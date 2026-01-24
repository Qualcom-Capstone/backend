# =============================================================================
# Speedcam MSA - GCP Deployment Makefile
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

# Infrastructure
DB_USER ?= sa
DB_PASSWORD ?= 1234
RABBITMQ_USER ?= sa
RABBITMQ_PASSWORD ?= 1234

# Colors for output
GREEN = \033[0;32m
YELLOW = \033[0;33m
RED = \033[0;31m
NC = \033[0m

.PHONY: help setup build push deploy clean

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
	@echo "  make build                    # Build all images"
	@echo "  make push                     # Push all images"
	@echo "  make deploy                   # Full deployment"
	@echo "  make deploy-main              # Deploy main service only"
	@echo "  make TAG=v1.0.0 build push    # Build and push with specific tag"

# =============================================================================
# Setup
# =============================================================================

setup: setup-gcloud setup-registry setup-firewall ## Initial GCP setup

setup-gcloud: ## Configure gcloud
	@echo "$(GREEN)Configuring gcloud...$(NC)"
	gcloud config set compute/region $(GCP_REGION)
	gcloud config set compute/zone $(GCP_ZONE)
	@echo "$(GREEN)Enabling required APIs...$(NC)"
	gcloud services enable compute.googleapis.com artifactregistry.googleapis.com

setup-registry: ## Create Artifact Registry
	@echo "$(GREEN)Creating Artifact Registry...$(NC)"
	-gcloud artifacts repositories create speedcam \
		--repository-format=docker \
		--location=$(GCP_REGION) \
		--description="Speedcam MSA Docker images" 2>/dev/null || true
	@echo "$(GREEN)Configuring Docker authentication...$(NC)"
	gcloud auth configure-docker $(GCP_REGION)-docker.pkg.dev --quiet

setup-firewall: ## Create firewall rules
	@echo "$(GREEN)Creating firewall rules...$(NC)"
	-gcloud compute firewall-rules create speedcam-internal \
		--network=default \
		--allow=tcp:3306,tcp:5672,tcp:1883,tcp:15672,tcp:8000 \
		--source-ranges=10.0.0.0/8 \
		--target-tags=speedcam 2>/dev/null || true
	-gcloud compute firewall-rules create speedcam-external \
		--network=default \
		--allow=tcp:8000,tcp:15672 \
		--source-ranges=0.0.0.0/0 \
		--target-tags=speedcam-web 2>/dev/null || true

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
# Deploy Infrastructure
# =============================================================================

deploy-infra: deploy-rabbitmq deploy-mysql init-infra ## Deploy infrastructure (RabbitMQ, MySQL)

deploy-rabbitmq: ## Deploy RabbitMQ instance
	@echo "$(GREEN)Deploying RabbitMQ...$(NC)"
	-gcloud compute instances delete speedcam-rabbitmq --zone=$(GCP_ZONE) --quiet 2>/dev/null || true
	gcloud compute instances create-with-container speedcam-rabbitmq \
		--zone=$(GCP_ZONE) \
		--machine-type=e2-small \
		--tags=speedcam,speedcam-web \
		--container-image=rabbitmq:3.13-management \
		--container-env="RABBITMQ_DEFAULT_USER=$(RABBITMQ_USER),RABBITMQ_DEFAULT_PASS=$(RABBITMQ_PASSWORD)"

deploy-mysql: ## Deploy MySQL instance
	@echo "$(GREEN)Deploying MySQL...$(NC)"
	-gcloud compute instances delete speedcam-mysql --zone=$(GCP_ZONE) --quiet 2>/dev/null || true
	gcloud compute instances create-with-container speedcam-mysql \
		--zone=$(GCP_ZONE) \
		--machine-type=e2-small \
		--tags=speedcam \
		--container-image=mysql:8.0 \
		--container-env="MYSQL_ROOT_PASSWORD=root,MYSQL_USER=$(DB_USER),MYSQL_PASSWORD=$(DB_PASSWORD),MYSQL_DATABASE=speedcam"

init-infra: ## Initialize infrastructure (MQTT plugin, databases)
	@echo "$(YELLOW)Waiting for instances to start...$(NC)"
	@sleep 60
	@echo "$(GREEN)Enabling MQTT plugin...$(NC)"
	gcloud compute ssh speedcam-rabbitmq --zone=$(GCP_ZONE) \
		--command="docker exec \$$(docker ps -q) rabbitmq-plugins enable rabbitmq_mqtt" || true
	@echo "$(GREEN)Creating databases...$(NC)"
	gcloud compute ssh speedcam-mysql --zone=$(GCP_ZONE) \
		--command="docker exec \$$(docker ps -q) mysql -u root -proot -e \"\
			CREATE DATABASE IF NOT EXISTS speedcam_vehicles; \
			CREATE DATABASE IF NOT EXISTS speedcam_detections; \
			CREATE DATABASE IF NOT EXISTS speedcam_notifications; \
			GRANT ALL PRIVILEGES ON speedcam_vehicles.* TO '$(DB_USER)'@'%'; \
			GRANT ALL PRIVILEGES ON speedcam_detections.* TO '$(DB_USER)'@'%'; \
			GRANT ALL PRIVILEGES ON speedcam_notifications.* TO '$(DB_USER)'@'%'; \
			FLUSH PRIVILEGES;\"" || true

# =============================================================================
# Deploy Services
# =============================================================================

deploy-services: get-ips deploy-main deploy-ocr deploy-alert migrate ## Deploy all services

get-ips: ## Get infrastructure internal IPs
	$(eval RABBITMQ_IP := $(shell gcloud compute instances describe speedcam-rabbitmq --zone=$(GCP_ZONE) --format='get(networkInterfaces[0].networkIP)' 2>/dev/null))
	$(eval MYSQL_IP := $(shell gcloud compute instances describe speedcam-mysql --zone=$(GCP_ZONE) --format='get(networkInterfaces[0].networkIP)' 2>/dev/null))
	@echo "RabbitMQ IP: $(RABBITMQ_IP)"
	@echo "MySQL IP: $(MYSQL_IP)"

deploy-main: get-ips ## Deploy main service
	@echo "$(GREEN)Deploying main service...$(NC)"
	-gcloud compute instances delete speedcam-main --zone=$(GCP_ZONE) --quiet 2>/dev/null || true
	gcloud compute instances create-with-container speedcam-main \
		--zone=$(GCP_ZONE) \
		--machine-type=e2-medium \
		--tags=speedcam,speedcam-web \
		--scopes=cloud-platform \
		--container-image=$(MAIN_IMAGE) \
		--container-env="\
DJANGO_SETTINGS_MODULE=config.settings.dev,\
DB_HOST=$(MYSQL_IP),DB_PORT=3306,\
DB_NAME=speedcam,DB_NAME_VEHICLES=speedcam_vehicles,\
DB_NAME_DETECTIONS=speedcam_detections,DB_NAME_NOTIFICATIONS=speedcam_notifications,\
DB_USER=$(DB_USER),DB_PASSWORD=$(DB_PASSWORD),\
CELERY_BROKER_URL=amqp://$(RABBITMQ_USER):$(RABBITMQ_PASSWORD)@$(RABBITMQ_IP):5672//,\
RABBITMQ_HOST=$(RABBITMQ_IP),MQTT_PORT=1883,\
MQTT_USER=$(RABBITMQ_USER),MQTT_PASS=$(RABBITMQ_PASSWORD),\
OCR_MOCK=true,FCM_MOCK=true"

deploy-ocr: get-ips ## Deploy OCR worker
	@echo "$(GREEN)Deploying OCR worker...$(NC)"
	-gcloud compute instances delete speedcam-ocr --zone=$(GCP_ZONE) --quiet 2>/dev/null || true
	gcloud compute instances create-with-container speedcam-ocr \
		--zone=$(GCP_ZONE) \
		--machine-type=e2-medium \
		--tags=speedcam \
		--scopes=cloud-platform \
		--container-image=$(OCR_IMAGE) \
		--container-env="\
DJANGO_SETTINGS_MODULE=config.settings.dev,\
DB_HOST=$(MYSQL_IP),DB_PORT=3306,\
DB_NAME=speedcam,DB_NAME_VEHICLES=speedcam_vehicles,\
DB_NAME_DETECTIONS=speedcam_detections,DB_NAME_NOTIFICATIONS=speedcam_notifications,\
DB_USER=$(DB_USER),DB_PASSWORD=$(DB_PASSWORD),\
CELERY_BROKER_URL=amqp://$(RABBITMQ_USER):$(RABBITMQ_PASSWORD)@$(RABBITMQ_IP):5672//,\
OCR_CONCURRENCY=2,OCR_MOCK=true"

deploy-alert: get-ips ## Deploy alert worker
	@echo "$(GREEN)Deploying alert worker...$(NC)"
	-gcloud compute instances delete speedcam-alert --zone=$(GCP_ZONE) --quiet 2>/dev/null || true
	gcloud compute instances create-with-container speedcam-alert \
		--zone=$(GCP_ZONE) \
		--machine-type=e2-small \
		--tags=speedcam \
		--scopes=cloud-platform \
		--container-image=$(ALERT_IMAGE) \
		--container-env="\
DJANGO_SETTINGS_MODULE=config.settings.dev,\
DB_HOST=$(MYSQL_IP),DB_PORT=3306,\
DB_NAME=speedcam,DB_NAME_VEHICLES=speedcam_vehicles,\
DB_NAME_DETECTIONS=speedcam_detections,DB_NAME_NOTIFICATIONS=speedcam_notifications,\
DB_USER=$(DB_USER),DB_PASSWORD=$(DB_PASSWORD),\
CELERY_BROKER_URL=amqp://$(RABBITMQ_USER):$(RABBITMQ_PASSWORD)@$(RABBITMQ_IP):5672//,\
ALERT_CONCURRENCY=50,FCM_MOCK=true"

migrate: ## Run Django migrations
	@echo "$(YELLOW)Waiting for main service to start...$(NC)"
	@sleep 45
	@echo "$(GREEN)Running migrations...$(NC)"
	gcloud compute ssh speedcam-main --zone=$(GCP_ZONE) \
		--command="docker exec \$$(docker ps -q) python manage.py makemigrations vehicles detections notifications 2>/dev/null || true"
	gcloud compute ssh speedcam-main --zone=$(GCP_ZONE) \
		--command="docker exec \$$(docker ps -q) python manage.py migrate --database=default --noinput"
	gcloud compute ssh speedcam-main --zone=$(GCP_ZONE) \
		--command="docker exec \$$(docker ps -q) python manage.py migrate vehicles --database=vehicles_db --noinput"
	gcloud compute ssh speedcam-main --zone=$(GCP_ZONE) \
		--command="docker exec \$$(docker ps -q) python manage.py migrate detections --database=detections_db --noinput"
	gcloud compute ssh speedcam-main --zone=$(GCP_ZONE) \
		--command="docker exec \$$(docker ps -q) python manage.py migrate notifications --database=notifications_db --noinput"

# =============================================================================
# Full Deployment
# =============================================================================

deploy: setup build push deploy-infra deploy-services status ## Full deployment (setup + build + push + deploy)
	@echo "$(GREEN)Deployment complete!$(NC)"

deploy-quick: build push restart-services ## Quick deployment (build + push + restart)
	@echo "$(GREEN)Quick deployment complete!$(NC)"

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

clean: clean-services clean-infra clean-firewall ## Clean all resources

clean-services: ## Delete service instances
	@echo "$(RED)Deleting service instances...$(NC)"
	-gcloud compute instances delete speedcam-main speedcam-ocr speedcam-alert \
		--zone=$(GCP_ZONE) --quiet 2>/dev/null || true

clean-infra: ## Delete infrastructure instances
	@echo "$(RED)Deleting infrastructure instances...$(NC)"
	-gcloud compute instances delete speedcam-rabbitmq speedcam-mysql \
		--zone=$(GCP_ZONE) --quiet 2>/dev/null || true

clean-firewall: ## Delete firewall rules
	@echo "$(RED)Deleting firewall rules...$(NC)"
	-gcloud compute firewall-rules delete speedcam-internal speedcam-external --quiet 2>/dev/null || true

clean-registry: ## Delete Artifact Registry
	@echo "$(RED)Deleting Artifact Registry...$(NC)"
	-gcloud artifacts repositories delete speedcam --location=$(GCP_REGION) --quiet 2>/dev/null || true

clean-all: clean clean-registry ## Clean everything including registry
	@echo "$(GREEN)All resources cleaned.$(NC)"

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
