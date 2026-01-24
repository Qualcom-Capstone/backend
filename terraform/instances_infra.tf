# =============================================================================
# Speedcam MSA - Infrastructure Instances (RabbitMQ, MySQL)
# =============================================================================

# =============================================================================
# RabbitMQ Instance
# =============================================================================

resource "google_compute_instance" "rabbitmq" {
  name         = "speedcam-rabbitmq"
  machine_type = var.machine_type_small
  zone         = var.zone
  project      = var.project_id

  tags = ["speedcam", "speedcam-web"]

  labels = merge(local.common_labels, {
    service = "rabbitmq"
  })

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
      size  = 20
      type  = "pd-standard"
    }
  }

  network_interface {
    network = var.network_name

    access_config {
      // Ephemeral public IP
    }
  }

  metadata = {
    gce-container-declaration = yamlencode({
      spec = {
        containers = [{
          name  = "rabbitmq"
          image = var.rabbitmq_image
          env = [
            { name = "RABBITMQ_DEFAULT_USER", value = var.rabbitmq_user },
            { name = "RABBITMQ_DEFAULT_PASS", value = var.rabbitmq_password },
          ]
          volumeMounts = []
        }]
        volumes = []
        restartPolicy = "Always"
      }
    })
  }

  service_account {
    email  = data.google_compute_default_service_account.default.email
    scopes = ["cloud-platform"]
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
    preemptible         = false
  }

  allow_stopping_for_update = true

  lifecycle {
    create_before_destroy = true
  }
}

# =============================================================================
# MySQL Instance
# =============================================================================

resource "google_compute_instance" "mysql" {
  name         = "speedcam-mysql"
  machine_type = var.machine_type_small
  zone         = var.zone
  project      = var.project_id

  tags = ["speedcam"]

  labels = merge(local.common_labels, {
    service = "mysql"
  })

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
      size  = 50
      type  = "pd-ssd"
    }
  }

  network_interface {
    network = var.network_name

    access_config {
      // Ephemeral public IP
    }
  }

  metadata = {
    gce-container-declaration = yamlencode({
      spec = {
        containers = [{
          name  = "mysql"
          image = var.mysql_image
          env = [
            { name = "MYSQL_ROOT_PASSWORD", value = var.db_root_password },
            { name = "MYSQL_DATABASE", value = var.db_name },
            { name = "MYSQL_USER", value = var.db_user },
            { name = "MYSQL_PASSWORD", value = var.db_password },
          ]
          volumeMounts = [{
            name      = "mysql-data"
            mountPath = "/var/lib/mysql"
          }]
        }]
        volumes = [{
          name = "mysql-data"
          hostPath = {
            path = "/var/lib/mysql"
          }
        }]
        restartPolicy = "Always"
      }
    })
  }

  service_account {
    email  = data.google_compute_default_service_account.default.email
    scopes = ["cloud-platform"]
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
    preemptible         = false
  }

  allow_stopping_for_update = true

  lifecycle {
    create_before_destroy = true
  }
}

# =============================================================================
# Null Resource for Infrastructure Initialization
# =============================================================================

# Wait for instances to be ready
resource "time_sleep" "wait_for_infra" {
  depends_on = [
    google_compute_instance.rabbitmq,
    google_compute_instance.mysql
  ]

  create_duration = "90s"
}

# Initialize RabbitMQ MQTT plugin
resource "null_resource" "init_rabbitmq" {
  depends_on = [time_sleep.wait_for_infra]

  provisioner "local-exec" {
    command = <<-EOT
      gcloud compute ssh speedcam-rabbitmq --zone=${var.zone} --project=${var.project_id} \
        --command="docker exec \$(docker ps -q) rabbitmq-plugins enable rabbitmq_mqtt" \
        || echo "MQTT plugin may already be enabled"
    EOT
  }

  triggers = {
    instance_id = google_compute_instance.rabbitmq.instance_id
  }
}

# Initialize MySQL databases
resource "null_resource" "init_mysql" {
  depends_on = [time_sleep.wait_for_infra]

  provisioner "local-exec" {
    command = <<-EOT
      gcloud compute ssh speedcam-mysql --zone=${var.zone} --project=${var.project_id} \
        --command="docker exec \$(docker ps -q) mysql -u root -p${var.db_root_password} -e \"\
          CREATE DATABASE IF NOT EXISTS ${var.db_name}_vehicles; \
          CREATE DATABASE IF NOT EXISTS ${var.db_name}_detections; \
          CREATE DATABASE IF NOT EXISTS ${var.db_name}_notifications; \
          GRANT ALL PRIVILEGES ON ${var.db_name}_vehicles.* TO '${var.db_user}'@'%'; \
          GRANT ALL PRIVILEGES ON ${var.db_name}_detections.* TO '${var.db_user}'@'%'; \
          GRANT ALL PRIVILEGES ON ${var.db_name}_notifications.* TO '${var.db_user}'@'%'; \
          FLUSH PRIVILEGES;\"" \
        || echo "Databases may already exist"
    EOT
  }

  triggers = {
    instance_id = google_compute_instance.mysql.instance_id
  }
}
