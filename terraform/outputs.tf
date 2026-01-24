# =============================================================================
# Speedcam MSA - Terraform Outputs
# =============================================================================

# =============================================================================
# Instance IPs
# =============================================================================

output "rabbitmq_internal_ip" {
  description = "RabbitMQ internal IP"
  value       = google_compute_instance.rabbitmq.network_interface[0].network_ip
}

output "rabbitmq_external_ip" {
  description = "RabbitMQ external IP"
  value       = google_compute_instance.rabbitmq.network_interface[0].access_config[0].nat_ip
}

output "mysql_internal_ip" {
  description = "MySQL internal IP"
  value       = google_compute_instance.mysql.network_interface[0].network_ip
}

output "mysql_external_ip" {
  description = "MySQL external IP"
  value       = google_compute_instance.mysql.network_interface[0].access_config[0].nat_ip
}

output "main_internal_ip" {
  description = "Main service internal IP"
  value       = google_compute_instance.main.network_interface[0].network_ip
}

output "main_external_ip" {
  description = "Main service external IP"
  value       = google_compute_instance.main.network_interface[0].access_config[0].nat_ip
}

output "ocr_internal_ip" {
  description = "OCR worker internal IP"
  value       = google_compute_instance.ocr.network_interface[0].network_ip
}

output "ocr_external_ip" {
  description = "OCR worker external IP"
  value       = google_compute_instance.ocr.network_interface[0].access_config[0].nat_ip
}

output "alert_internal_ip" {
  description = "Alert worker internal IP"
  value       = google_compute_instance.alert.network_interface[0].network_ip
}

output "alert_external_ip" {
  description = "Alert worker external IP"
  value       = google_compute_instance.alert.network_interface[0].access_config[0].nat_ip
}

# =============================================================================
# Service URLs
# =============================================================================

output "api_url" {
  description = "API base URL"
  value       = "http://${google_compute_instance.main.network_interface[0].access_config[0].nat_ip}:8000"
}

output "swagger_url" {
  description = "Swagger UI URL"
  value       = "http://${google_compute_instance.main.network_interface[0].access_config[0].nat_ip}:8000/swagger/"
}

output "health_url" {
  description = "Health check URL"
  value       = "http://${google_compute_instance.main.network_interface[0].access_config[0].nat_ip}:8000/health/"
}

output "rabbitmq_management_url" {
  description = "RabbitMQ Management UI URL"
  value       = "http://${google_compute_instance.rabbitmq.network_interface[0].access_config[0].nat_ip}:15672"
}

# =============================================================================
# Registry
# =============================================================================

output "registry_url" {
  description = "Artifact Registry URL"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.registry_name}"
}

# =============================================================================
# Connection Strings
# =============================================================================

output "celery_broker_url" {
  description = "Celery broker URL (internal)"
  value       = "amqp://${var.rabbitmq_user}:****@${google_compute_instance.rabbitmq.network_interface[0].network_ip}:5672//"
  sensitive   = false
}

output "mysql_connection_string" {
  description = "MySQL connection string (internal)"
  value       = "mysql://${var.db_user}:****@${google_compute_instance.mysql.network_interface[0].network_ip}:3306/${var.db_name}"
  sensitive   = false
}

# =============================================================================
# Summary
# =============================================================================

output "deployment_summary" {
  description = "Deployment summary"
  value = <<-EOT

    ===========================================
    Speedcam MSA Deployment Summary
    ===========================================

    Project:     ${var.project_id}
    Region:      ${var.region}
    Zone:        ${var.zone}
    Environment: ${var.environment}

    -------------------------------------------
    Infrastructure
    -------------------------------------------
    RabbitMQ:    ${google_compute_instance.rabbitmq.network_interface[0].network_ip} (${google_compute_instance.rabbitmq.network_interface[0].access_config[0].nat_ip})
    MySQL:       ${google_compute_instance.mysql.network_interface[0].network_ip} (${google_compute_instance.mysql.network_interface[0].access_config[0].nat_ip})

    -------------------------------------------
    Services
    -------------------------------------------
    Main:        ${google_compute_instance.main.network_interface[0].network_ip} (${google_compute_instance.main.network_interface[0].access_config[0].nat_ip})
    OCR:         ${google_compute_instance.ocr.network_interface[0].network_ip} (${google_compute_instance.ocr.network_interface[0].access_config[0].nat_ip})
    Alert:       ${google_compute_instance.alert.network_interface[0].network_ip} (${google_compute_instance.alert.network_interface[0].access_config[0].nat_ip})

    -------------------------------------------
    URLs
    -------------------------------------------
    API:         http://${google_compute_instance.main.network_interface[0].access_config[0].nat_ip}:8000/
    Swagger:     http://${google_compute_instance.main.network_interface[0].access_config[0].nat_ip}:8000/swagger/
    Health:      http://${google_compute_instance.main.network_interface[0].access_config[0].nat_ip}:8000/health/
    RabbitMQ:    http://${google_compute_instance.rabbitmq.network_interface[0].access_config[0].nat_ip}:15672/

    ===========================================

  EOT
}
