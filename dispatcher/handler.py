import json
import os
import boto3

def lambda_handler(event, context):
    print("Received event:", json.dumps(event))
    
    # Configure boto3 to use LocalStack endpoints
    # When running inside LocalStack, we can use the AWS_ENDPOINT_URL environment variable 
    # or just point it to the localstack host. LocalStack sets AWS_ENDPOINT_URL automatically,
    # but we can explicitly set it if needed.
    endpoint_url = os.environ.get('AWS_ENDPOINT_URL', f"http://{os.environ.get('LOCALSTACK_HOSTNAME', 'localhost')}:4566")
    
    sqs = boto3.client('sqs', endpoint_url=endpoint_url)
    queue_url = os.environ['QUEUE_URL']

    for record in event.get('Records', []):
        if record.get('eventName', '').startswith('ObjectCreated:'):
            bucket_name = record['s3']['bucket']['name']
            object_key = record['s3']['object']['key']
            
            message = {
                'bucket': bucket_name,
                'key': object_key
            }
            
            print(f"Sending message to SQS: {message}")
            
            response = sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(message)
            )
            print(f"SQS response: {response}")

    return {
        'statusCode': 200,
        'body': json.dumps('Successfully dispatched event')
    }
