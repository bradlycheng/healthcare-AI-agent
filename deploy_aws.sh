#!/bin/bash
# deploy_aws.sh - Utility to push your agent to Amazon ECR

# CHANGE THESE VARIABLES
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID="087607092792" # Get this from AWS Console
IMAGE_NAME="healthcare-ai-app"

echo "Logging into Amazon ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

echo "Building Docker Image..."
docker build -t $IMAGE_NAME .

echo "Tagging Image for ECR..."
docker tag $IMAGE_NAME:latest $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$IMAGE_NAME:latest

echo "Pushing Image..."
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$IMAGE_NAME:latest

echo "Deployment complete! Your image is now in AWS ECR."
echo "Now use the 'ec2_setup.sh' script to launch your instance."
