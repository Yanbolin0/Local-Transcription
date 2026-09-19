import os
import json
import time
import boto3
import whisper
import warnings
from botocore.exceptions import ClientError

# Suppress FP16 warnings on CPU, though user has a GPU
warnings.filterwarnings("ignore", message="FP16 is not supported on CPU; using FP32 instead")

# Configuration
LOCALSTACK_ENDPOINT = os.environ.get("LOCALSTACK_ENDPOINT", "http://localhost:4566")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
QUEUE_NAME = "transcription-queue-v2"
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "medium") # Can be tiny, base, small, medium, large

# Initialize AWS clients for LocalStack
boto_config = {
    "endpoint_url": LOCALSTACK_ENDPOINT,
    "region_name": REGION,
    "aws_access_key_id": "test",
    "aws_secret_access_key": "test",
}

s3_client = boto3.client("s3", **boto_config)
sqs_client = boto3.client("sqs", **boto_config)

def get_queue_url():
    response = sqs_client.get_queue_url(QueueName=QUEUE_NAME)
    return response['QueueUrl']

def process_message(message, model):
    body = json.loads(message['Body'])
    bucket_name = body['bucket']
    object_key = body['key']
    
    print(f"Processing audio file: s3://{bucket_name}/{object_key}")
    
    # Generate local paths
    filename = os.path.basename(object_key)
    local_audio_path = f"/tmp/{filename}" if os.name != 'nt' else f"temp_{filename}"
    local_transcript_path = f"{local_audio_path}.txt"
    
    try:
        # Download from S3
        print(f"Downloading {object_key}...")
        s3_client.download_file(bucket_name, object_key, local_audio_path)
        
        # Transcribe
        print("Transcribing with Whisper...")
        # device will automatically be 'cuda' if available, otherwise 'cpu'
        result = model.transcribe(local_audio_path)
        transcript_text = result["text"]
        
        # Save transcript locally
        with open(local_transcript_path, "w", encoding="utf-8") as f:
            f.write(transcript_text)
            
        # Upload transcript to S3
        # Assuming original key was 'audio-input/file.mp3', new key will be 'whisper-transcriptions/file.mp3.txt'
        base_name = os.path.basename(object_key)
        transcript_key = f"whisper-transcriptions/{base_name}.txt"
        
        print(f"Uploading transcript to s3://{bucket_name}/{transcript_key}")
        s3_client.upload_file(local_transcript_path, bucket_name, transcript_key)
        
        print("Processing completed successfully.")
        return True
        
    except Exception as e:
        print(f"Error processing message: {e}")
        return False
    finally:
        # Cleanup local files
        if os.path.exists(local_audio_path):
            os.remove(local_audio_path)
        if os.path.exists(local_transcript_path):
            os.remove(local_transcript_path)


def main():
    print(f"Loading Whisper model '{WHISPER_MODEL}'...")
    # This will load the model onto the GPU if available (NVIDIA RTX 4070)
    model = whisper.load_model(WHISPER_MODEL)
    print("Model loaded.")

    queue_url = None
    while not queue_url:
        try:
            queue_url = get_queue_url()
            print(f"Listening to queue: {queue_url}")
        except ClientError as e:
            print(f"Queue not ready yet. Retrying in 5 seconds... (Error: {e})")
            time.sleep(5)

    while True:
        try:
            # Poll SQS
            response = sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=10 # Long polling
            )

            messages = response.get('Messages', [])
            
            if not messages:
                # print("No messages in queue, waiting...")
                continue
                
            for message in messages:
                receipt_handle = message['ReceiptHandle']
                
                success = process_message(message, model)
                
                if success:
                    # Delete message from queue
                    sqs_client.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=receipt_handle
                    )
                    print("Message deleted from queue.")

        except Exception as e:
            print(f"Error in polling loop: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
