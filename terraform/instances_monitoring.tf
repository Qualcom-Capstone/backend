# =============================================================================
# DataDog Agent Instance
# =============================================================================

resource "google_compute_instance" "datadog_agent" {
  name         = "speedcam-datadog"
  machine_type = var.machine_type_small
  zone         = var.zone

  tags = ["speedcam"]

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
      size  = 20
    }
  }

  network_interface {
    network = "default"
    access_config {}
  }

  metadata = {
    gce-container-declaration = yamlencode({
      spec = {
        containers = [{
          name  = "datadog-agent"
          image = "gcr.io/datadoghq/agent:7"
          env = [
            { name = "DD_API_KEY", value = var.dd_api_key },
            { name = "DD_SITE", value = var.dd_site },
            { name = "DD_APM_ENABLED", value = "true" },
            { name = "DD_APM_NON_LOCAL_TRAFFIC", value = "true" },
            { name = "DD_DOGSTATSD_NON_LOCAL_TRAFFIC", value = "true" },
            { name = "DD_LOGS_ENABLED", value = "true" },
            { name = "DD_ENV", value = var.environment },
          ]
        }]
        restartPolicy = "Always"
      }
    })
  }

  labels = {
    project     = "speedcam"
    environment = var.environment
    service     = "datadog"
    managed_by  = "terraform"
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
    preemptible         = false
  }

  service_account {
    scopes = ["cloud-platform"]
  }
}
