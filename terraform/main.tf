# =============================================================================
# Speedcam MSA - Terraform Main Configuration
# =============================================================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  # Optional: Configure backend for state management
  # backend "gcs" {
  #   bucket = "your-terraform-state-bucket"
  #   prefix = "speedcam/state"
  # }
}

# =============================================================================
# Provider Configuration
# =============================================================================

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# =============================================================================
# Data Sources
# =============================================================================

data "google_project" "current" {
  project_id = var.project_id
}

data "google_compute_default_service_account" "default" {
  project = var.project_id
}

# =============================================================================
# Local Values
# =============================================================================

locals {
  # Common labels for all resources
  common_labels = {
    project     = "speedcam"
    environment = var.environment
    managed_by  = "terraform"
  }

  # Container registry path
  registry = "${var.region}-docker.pkg.dev/${var.project_id}/${var.registry_name}"

  # Service environment variables (common)
  common_env = {
    DJANGO_SETTINGS_MODULE   = "config.settings.${var.environment}"
    DB_HOST                  = google_compute_instance.mysql.network_interface[0].network_ip
    DB_PORT                  = "3306"
    DB_NAME                  = var.db_name
    DB_NAME_VEHICLES         = "${var.db_name}_vehicles"
    DB_NAME_DETECTIONS       = "${var.db_name}_detections"
    DB_NAME_NOTIFICATIONS    = "${var.db_name}_notifications"
    DB_USER                  = var.db_user
    DB_PASSWORD              = var.db_password
    CELERY_BROKER_URL        = "amqp://${var.rabbitmq_user}:${var.rabbitmq_password}@${google_compute_instance.rabbitmq.network_interface[0].network_ip}:5672//"
    DD_AGENT_HOST            = google_compute_instance.datadog_agent.network_interface[0].network_ip
    DD_TRACE_AGENT_PORT      = "8126"
    DD_ENV                   = var.environment
    DD_LOGS_INJECTION        = "true"
    DD_TRACE_SAMPLE_RATE     = "1"
    DD_PROFILING_ENABLED     = "true"
    _DD_TRACE_WRITER_NATIVE  = "false"
  }
}
