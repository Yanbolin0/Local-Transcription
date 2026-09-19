provider "aws" {
  access_key                  = "test"
  secret_key                  = "test"
  region                      = "us-east-1"
  s3_use_path_style           = true
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    s3     = "http://localhost:4566"
    sqs    = "http://localhost:4566"
    lambda = "http://localhost:4566"
    iam    = "http://localhost:4566"
  }
}

resource "aws_s3_bucket" "transcription_bucket" {
  bucket = "audio-transcription-bucket"
}

resource "aws_sqs_queue" "transcription_queue" {
  name = "transcription-queue"
}

# IAM Role for Lambda
resource "aws_iam_role" "lambda_exec" {
  name = "lambda-dispatcher-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# Archive for Lambda
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "../dispatcher"
  output_path = "dispatcher.zip"
}

# Lambda Function
resource "aws_lambda_function" "dispatcher" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "audio-dispatcher"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.9"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      QUEUE_URL = aws_sqs_queue.transcription_queue.url
    }
  }
}

# Lambda permission to allow S3 to invoke it
resource "aws_lambda_permission" "allow_bucket" {
  statement_id  = "AllowExecutionFromS3Bucket"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dispatcher.arn
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.transcription_bucket.arn
}

# S3 Event Notification to Lambda
resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = aws_s3_bucket.transcription_bucket.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.dispatcher.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "audio-input/"
  }

  depends_on = [aws_lambda_permission.allow_bucket]
}
