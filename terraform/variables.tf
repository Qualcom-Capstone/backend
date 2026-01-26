# =============================================================================
# Speedcam MSA - Terraform Variables
# =============================================================================

# =============================================================================
# Project Configuration
# =============================================================================

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "asia-northeast3"
}

variable "zone" {
  description = "GCP Zone"
  type        = string
  default     = "asia-northeast3-a"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

# =============================================================================
# Network Configuration
# =============================================================================

variable "network_name" {
  description = "VPC Network name"
  type        = string
  default     = "default"
}

# =============================================================================
# Artifact Registry Configuration
# =============================================================================

variable "registry_name" {
  description = "Artifact Registry repository name"
  type        = string
  default     = "speedcam"
}

# =============================================================================
# Database Configuration
# =============================================================================

variable "db_name" {
  description = "Base database name"
  type        = string
  default     = "speedcam"
}

variable "db_user" {
  description = "Database user"
  type        = string
  default     = "sa"
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
  default     = "1234"
}

variable "db_root_password" {
  description = "Database root password"
  type        = string
  sensitive   = true
  default     = "root"
}

# =============================================================================
# RabbitMQ Configuration
# =============================================================================

variable "rabbitmq_user" {
  description = "RabbitMQ user"
  type        = string
  default     = "sa"
}

variable "rabbitmq_password" {
  description = "RabbitMQ password"
  type        = string
  sensitive   = true
  default     = "1234"
}

# =============================================================================
# Instance Configuration
# =============================================================================

variable "machine_type_small" {
  description = "Machine type for small instances"
  type        = string
  default     = "e2-small"
}

variable "machine_type_medium" {
  description = "Machine type for medium instances"
  type        = string
  default     = "e2-medium"
}

# =============================================================================
# Container Images
# =============================================================================

variable "image_tag" {
  description = "Docker image tag"
  type        = string
  default     = "latest"
}

variable "mysql_image" {
  description = "MySQL Docker image"
  type        = string
  default     = "mysql:8.0"
}

variable "rabbitmq_image" {
  description = "RabbitMQ Docker image"
  type        = string
  default     = "rabbitmq:3.13-management"
}

# =============================================================================
# Application Configuration
# =============================================================================

variable "ocr_concurrency" {
  description = "OCR worker concurrency"
  type        = number
  default     = 2
}

variable "alert_concurrency" {
  description = "Alert worker concurrency"
  type        = number
  default     = 50
}

variable "ocr_mock" {
  description = "Enable OCR mock mode"
  type        = bool
  default     = true
}

variable "fcm_mock" {
  description = "Enable FCM mock mode"
  type        = bool
  default     = true
}

# =============================================================================
# DataDog
# =============================================================================

variable "dd_api_key" {
  description = "DataDog API Key"
  type        = string
  sensitive   = true
}

variable "dd_site" {
  description = "DataDog site (e.g., ap1.datadoghq.com)"
  type        = string
  default     = "ap1.datadoghq.com"
}
