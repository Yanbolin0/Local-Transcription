import boto3
import json
import zipfile
import os
import time

LOCALSTACK_ENDPOINT = "http://localhost:4566"
REGION = "us-east-1"

boto_config = {
    "endpoint_url": LOCALSTACK_ENDPOINT,
    "region_name": REGION,
    "aws_access_key_id": "test",
    "aws_secret_access_key": "test",
}

s3 = boto3.client("s3", **boto_config)
sqs = boto3.client("sqs", **boto_config)
lambda_client = boto3.client("lambda", **boto_config)
iam = boto3.client("iam", **boto_config)

def setup():
    print("1. Creating SQS Queue...")
    queue_res = sqs.create_queue(QueueName="transcription-queue-v2")
    queue_url = queue_res["QueueUrl"]
    print(f"Queue URL: {queue_url}")

    print("2. Creating S3 Bucket...")
    try:
        s3.create_bucket(Bucket="audio-transcription-bucket-v2")
    except Exception as e:
        print(f"Bucket might already exist: {e}")
    
    print("3. Creating IAM Role for Lambda...")
    assume_role_policy = {
        "Version": "2012-10-17",
        "Statement": [{"Action": "sts:AssumeRole", "Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}}]
    }
    try:
        role_res = iam.create_role(
            RoleName="lambda-dispatcher-role-v2",
            AssumeRolePolicyDocument=json.dumps(assume_role_policy)
        )
        role_arn = role_res["Role"]["Arn"]
    except iam.exceptions.EntityAlreadyExistsException:
        role_arn = iam.get_role(RoleName="lambda-dispatcher-role-v2")["Role"]["Arn"]

    print("4. Packaging Lambda Function...")
    with zipfile.ZipFile("dispatcher.zip", "w") as z:
        z.write("../dispatcher/handler.py", "handler.py")
        
    with open("dispatcher.zip", "rb") as f:
        zip_bytes = f.read()

    print("5. Deploying Lambda Function...")
    try:
        lambda_res = lambda_client.create_function(
            FunctionName="audio-dispatcher-v2",
            Runtime="python3.9",
            Role=role_arn,
            Handler="handler.lambda_handler",
            Code={"ZipFile": zip_bytes},
            Environment={"Variables": {"QUEUE_URL": queue_url}}
        )
        lambda_arn = lambda_res["FunctionArn"]
    except lambda_client.exceptions.ResourceConflictException:
        pass # Ignore for now, assume created

    print("Waiting for Lambda to become active...")
    time.sleep(2)
    lambda_arn = lambda_client.get_function(FunctionName="audio-dispatcher-v2")["Configuration"]["FunctionArn"]
    
    print("6. Granting S3 permission to invoke Lambda...")
    try:
        lambda_client.add_permission(
            FunctionName="audio-dispatcher-v2",
            StatementId="AllowExecutionFromS3Bucket",
            Action="lambda:InvokeFunction",
            Principal="s3.amazonaws.com",
            SourceArn="arn:aws:s3:::audio-transcription-bucket-v2"
        )
    except lambda_client.exceptions.ResourceConflictException:
        pass # Permission already exists

    print("Waiting 3 seconds for IAM and Resource Policies to propagate...")
    time.sleep(3)

    print("7. Configuring S3 Event Notification...")
    s3.put_bucket_notification_configuration(
        Bucket="audio-transcription-bucket-v2",
        NotificationConfiguration={
            "LambdaFunctionConfigurations": [
                {
                    "LambdaFunctionArn": lambda_arn,
                    "Events": ["s3:ObjectCreated:*"],
                    "Filter": {
                        "Key": {
                            "FilterRules": [
                                {"Name": "prefix", "Value": "audio-input/"}
                            ]
                        }
                    }
                }
            ]
        }
    )
    print("Setup completed successfully!")

if __name__ == "__main__":
    setup()
