# =============================================================================
# Speedcam MSA - Network Configuration
# =============================================================================

# =============================================================================
# Firewall Rules
# =============================================================================

# Internal communication between services
resource "google_compute_firewall" "speedcam_internal" {
  name    = "speedcam-internal"
  network = var.network_name
  project = var.project_id

  description = "Allow internal communication for Speedcam MSA"

  allow {
    protocol = "tcp"
    ports    = ["3306", "5672", "1883", "15672", "8000", "8126"]
  }

  allow {
    protocol = "udp"
    ports    = ["8125"]
  }

  source_ranges = ["10.0.0.0/8"]
  target_tags   = ["speedcam"]

  priority = 1000
}

# External access for API and RabbitMQ Management
resource "google_compute_firewall" "speedcam_external" {
  name    = "speedcam-external"
  network = var.network_name
  project = var.project_id

  description = "Allow external access for Speedcam API and RabbitMQ Management"

  allow {
    protocol = "tcp"
    ports    = ["8000", "15672"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["speedcam-web"]

  priority = 1000
}

# SSH access (optional - for debugging)
resource "google_compute_firewall" "speedcam_ssh" {
  name    = "speedcam-ssh"
  network = var.network_name
  project = var.project_id

  description = "Allow SSH access to Speedcam instances"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["speedcam"]

  priority = 1000
}
