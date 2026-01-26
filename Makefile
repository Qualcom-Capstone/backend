# =============================================================================
# Speedcam MSA - Build & Operations Makefile
# =============================================================================

# Configuration
GCP_PROJECT_ID ?= $(shell gcloud config get-value project 2>/dev/null)
GCP_REGION ?= asia-northeast3
GCP_ZONE ?= asia-northeast3-a
REGISTRY ?= $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT_ID)/speedcam

# Image Tags
TAG ?= latest
MAIN_IMAGE = $(REGISTRY)/main:$(TAG)
OCR_IMAGE = $(REGISTRY)/ocr:$(TAG)
ALERT_IMAGE = $(REGISTRY)/alert:$(TAG)

# Colors for output
GREEN = \033[0;32m
YELLOW = \033[0;33m
RED = \033[0;31m
NC = \033[0m

.PHONY: help build push clean tf-init tf-plan tf-apply tf-destroy tf-output restart-services restart-main restart-ocr restart-alert status health dev-up dev-down dev-logs dev-build

# =============================================================================
# Help
# =============================================================================

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Examples:"
	@echo "  make build push restart-services  # Build, push, and restart (image update)"
	@echo "  make tf-plan                      # Preview infrastructure changes"
	@echo "  make tf-apply                     # Apply infrastructure changes"
	@echo "  make TAG=v1.0.0 build push        # Build and push with specific tag"

# =============================================================================
# Build
# =============================================================================

build: build-main build-ocr build-alert ## Build all Docker images

build-main: ## Build main service image
	@echo "$(GREEN)Building main image...$(NC)"
	docker build --platform linux/amd64 \
		-t $(MAIN_IMAGE) \
		-f docker/Dockerfile.main .

build-ocr: ## Build OCR worker image
	@echo "$(GREEN)Building OCR image...$(NC)"
	docker build --platform linux/amd64 \
		-t $(OCR_IMAGE) \
		-f docker/Dockerfile.ocr .

build-alert: ## Build alert worker image
	@echo "$(GREEN)Building alert image...$(NC)"
	docker build --platform linux/amd64 \
		-t $(ALERT_IMAGE) \
		-f docker/Dockerfile.alert .

# =============================================================================
# Push
# =============================================================================

push: push-main push-ocr push-alert ## Push all Docker images

push-main: ## Push main service image
	@echo "$(GREEN)Pushing main image...$(NC)"
	docker push $(MAIN_IMAGE)

push-ocr: ## Push OCR worker image
	@echo "$(GREEN)Pushing OCR image...$(NC)"
	docker push $(OCR_IMAGE)

push-alert: ## Push alert worker image
	@echo "$(GREEN)Pushing alert image...$(NC)"
	docker push $(ALERT_IMAGE)

# =============================================================================
# Terraform (Infrastructure Management)
# =============================================================================

TF_DIR = terraform

tf-init: ## Initialize Terraform
	cd $(TF_DIR) && terraform init

tf-plan: ## Preview infrastructure changes
	cd $(TF_DIR) && terraform plan

tf-apply: ## Apply infrastructure changes
	cd $(TF_DIR) && terraform apply

tf-destroy: ## Destroy all infrastructure
	cd $(TF_DIR) && terraform destroy

tf-output: ## Show Terraform outputs
	cd $(TF_DIR) && terraform output

# =============================================================================
# Operations
# =============================================================================

restart-services: ## Restart all service instances
	@echo "$(GREEN)Restarting services...$(NC)"
	gcloud compute instances reset speedcam-main speedcam-ocr speedcam-alert --zone=$(GCP_ZONE)

restart-main: ## Restart main service
	gcloud compute instances reset speedcam-main --zone=$(GCP_ZONE)

restart-ocr: ## Restart OCR worker
	gcloud compute instances reset speedcam-ocr --zone=$(GCP_ZONE)

restart-alert: ## Restart alert worker
	gcloud compute instances reset speedcam-alert --zone=$(GCP_ZONE)

status: ## Show deployment status
	@echo "$(GREEN)Instance Status:$(NC)"
	@gcloud compute instances list --filter="name~speedcam" \
		--format="table(name,zone,machineType,status,networkInterfaces[0].networkIP,networkInterfaces[0].accessConfigs[0].natIP)"
	@echo ""
	@echo "$(GREEN)Service URLs:$(NC)"
	@MAIN_IP=$$(gcloud compute instances describe speedcam-main --zone=$(GCP_ZONE) --format='get(networkInterfaces[0].accessConfigs[0].natIP)' 2>/dev/null); \
	RMQ_IP=$$(gcloud compute instances describe speedcam-rabbitmq --zone=$(GCP_ZONE) --format='get(networkInterfaces[0].accessConfigs[0].natIP)' 2>/dev/null); \
	echo "  API:      http://$$MAIN_IP:8000/"; \
	echo "  Swagger:  http://$$MAIN_IP:8000/swagger/"; \
	echo "  Health:   http://$$MAIN_IP:8000/health/"; \
	echo "  RabbitMQ: http://$$RMQ_IP:15672/"

health: ## Check health of all services
	@echo "$(GREEN)Checking health...$(NC)"
	@MAIN_IP=$$(gcloud compute instances describe speedcam-main --zone=$(GCP_ZONE) --format='get(networkInterfaces[0].accessConfigs[0].natIP)' 2>/dev/null); \
	curl -s http://$$MAIN_IP:8000/health/ && echo ""

logs-main: ## Show main service logs
	gcloud compute ssh speedcam-main --zone=$(GCP_ZONE) \
		--command="docker logs \$$(docker ps -q) 2>&1 | tail -50"

logs-ocr: ## Show OCR worker logs
	gcloud compute ssh speedcam-ocr --zone=$(GCP_ZONE) \
		--command="docker logs \$$(docker ps -q) 2>&1 | tail -50"

logs-alert: ## Show alert worker logs
	gcloud compute ssh speedcam-alert --zone=$(GCP_ZONE) \
		--command="docker logs \$$(docker ps -q) 2>&1 | tail -50"

ssh-main: ## SSH into main instance
	gcloud compute ssh speedcam-main --zone=$(GCP_ZONE)

ssh-ocr: ## SSH into OCR instance
	gcloud compute ssh speedcam-ocr --zone=$(GCP_ZONE)

ssh-alert: ## SSH into alert instance
	gcloud compute ssh speedcam-alert --zone=$(GCP_ZONE)

# =============================================================================
# Cleanup
# =============================================================================

clean: ## Destroy infrastructure (use 'make tf-destroy' instead)
	@echo "$(YELLOW)Infrastructure is now managed by Terraform.$(NC)"
	@echo "$(YELLOW)Please use 'make tf-destroy' to destroy all resources.$(NC)"

clean-services: ## Note: Services are managed by Terraform
	@echo "$(YELLOW)Services are now managed by Terraform.$(NC)"
	@echo "$(YELLOW)Please use 'make tf-destroy' to destroy all resources.$(NC)"

clean-infra: ## Note: Infrastructure is managed by Terraform
	@echo "$(YELLOW)Infrastructure is now managed by Terraform.$(NC)"
	@echo "$(YELLOW)Please use 'make tf-destroy' to destroy all resources.$(NC)"

clean-firewall: ## Note: Firewall rules are managed by Terraform
	@echo "$(YELLOW)Firewall rules are now managed by Terraform.$(NC)"
	@echo "$(YELLOW)Please use 'make tf-destroy' to destroy all resources.$(NC)"

clean-registry: ## Delete Artifact Registry (not managed by Terraform)
	@echo "$(RED)Deleting Artifact Registry...$(NC)"
	-gcloud artifacts repositories delete speedcam --location=$(GCP_REGION) --quiet 2>/dev/null || true

clean-all: clean clean-registry ## Note: Infrastructure is managed by Terraform
	@echo "$(YELLOW)Infrastructure is now managed by Terraform.$(NC)"
	@echo "$(YELLOW)Use 'make tf-destroy' to destroy infrastructure, then 'make clean-registry' for registry.$(NC)"

# =============================================================================
# Local Development
# =============================================================================

dev-up: ## Start local development environment
	docker-compose -f docker/docker-compose.yml up -d

dev-down: ## Stop local development environment
	docker-compose -f docker/docker-compose.yml down

dev-logs: ## Show local development logs
	docker-compose -f docker/docker-compose.yml logs -f

dev-build: ## Build local development images
	docker-compose -f docker/docker-compose.yml build
