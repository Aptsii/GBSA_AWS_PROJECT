#!/bin/sh
set -eu

bucket="iep-local-contract-fixtures"
awslocal s3api head-bucket --bucket "$bucket" >/dev/null 2>&1 || awslocal s3api create-bucket \
  --bucket "$bucket" \
  --create-bucket-configuration LocationConstraint="${AWS_DEFAULT_REGION:-ap-northeast-2}"
awslocal s3api put-bucket-cors --bucket "$bucket" --cors-configuration '{
  "CORSRules": [{
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "HEAD", "PUT"],
    "AllowedOrigins": ["http://localhost:5173", "http://localhost:5174"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }]
}'
