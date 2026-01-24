# =============================================================================
# Speedcam MSA - Service Instances (Main, OCR, Alert)
# =============================================================================

# =============================================================================
# Main Service Instance
# =============================================================================

resource "google_compute_instance" "main" {
  name         = "speedcam-main"
  machine_type = var.machine_type_medium
  zone         = var.zone
  project      = var.project_id

  depends_on = [
    null_resource.init_rabbitmq,
    null_resource.init_mysql
  ]

  tags = ["speedcam", "speedcam-web"]

  labels = merge(local.common_labels, {
    service = "main"
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
          name  = "main"
          image = "${local.registry}/main:${var.image_tag}"
          env = concat([
            for k, v in local.common_env : { name = k, value = v }
          ], [
            { name = "RABBITMQ_HOST", value = google_compute_instance.rabbitmq.network_interface[0].network_ip },
            { name = "MQTT_PORT", value = "1883" },
            { name = "MQTT_USER", value = var.rabbitmq_user },
            { name = "MQTT_PASS", value = var.rabbitmq_password },
            { name = "OCR_MOCK", value = tostring(var.ocr_mock) },
            { name = "FCM_MOCK", value = tostring(var.fcm_mock) },
          ])
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
}

# =============================================================================
# OCR Worker Instance
# =============================================================================

resource "google_compute_instance" "ocr" {
  name         = "speedcam-ocr"
  machine_type = var.machine_type_medium
  zone         = var.zone
  project      = var.project_id

  depends_on = [
    null_resource.init_rabbitmq,
    null_resource.init_mysql
  ]

  tags = ["speedcam"]

  labels = merge(local.common_labels, {
    service = "ocr"
  })

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
      size  = 30
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
          name  = "ocr"
          image = "${local.registry}/ocr:${var.image_tag}"
          env = concat([
            for k, v in local.common_env : { name = k, value = v }
          ], [
            { name = "OCR_CONCURRENCY", value = tostring(var.ocr_concurrency) },
            { name = "OCR_MOCK", value = tostring(var.ocr_mock) },
          ])
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
}

# =============================================================================
# Alert Worker Instance
# =============================================================================

resource "google_compute_instance" "alert" {
  name         = "speedcam-alert"
  machine_type = var.machine_type_small
  zone         = var.zone
  project      = var.project_id

  depends_on = [
    null_resource.init_rabbitmq,
    null_resource.init_mysql
  ]

  tags = ["speedcam"]

  labels = merge(local.common_labels, {
    service = "alert"
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
          name  = "alert"
          image = "${local.registry}/alert:${var.image_tag}"
          env = concat([
            for k, v in local.common_env : { name = k, value = v }
          ], [
            { name = "ALERT_CONCURRENCY", value = tostring(var.alert_concurrency) },
            { name = "FCM_MOCK", value = tostring(var.fcm_mock) },
          ])
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
}

# =============================================================================
# Django Migrations
# =============================================================================

resource "time_sleep" "wait_for_main" {
  depends_on = [google_compute_instance.main]

  create_duration = "60s"
}

resource "null_resource" "run_migrations" {
  depends_on = [time_sleep.wait_for_main]

  provisioner "local-exec" {
    command = <<-EOT
      # Create migrations
      gcloud compute ssh speedcam-main --zone=${var.zone} --project=${var.project_id} \
        --command="docker exec \$(docker ps -q) python manage.py makemigrations vehicles detections notifications 2>/dev/null || true"

      # Run migrations
      gcloud compute ssh speedcam-main --zone=${var.zone} --project=${var.project_id} \
        --command="docker exec \$(docker ps -q) python manage.py migrate --database=default --noinput"

      gcloud compute ssh speedcam-main --zone=${var.zone} --project=${var.project_id} \
        --command="docker exec \$(docker ps -q) python manage.py migrate vehicles --database=vehicles_db --noinput"

      gcloud compute ssh speedcam-main --zone=${var.zone} --project=${var.project_id} \
        --command="docker exec \$(docker ps -q) python manage.py migrate detections --database=detections_db --noinput"

      gcloud compute ssh speedcam-main --zone=${var.zone} --project=${var.project_id} \
        --command="docker exec \$(docker ps -q) python manage.py migrate notifications --database=notifications_db --noinput"
    EOT
  }

  triggers = {
    main_instance_id = google_compute_instance.main.instance_id
  }
}
