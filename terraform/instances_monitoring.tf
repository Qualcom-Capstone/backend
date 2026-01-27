# =============================================================================
# DataDog Agent Instance
# =============================================================================

resource "google_compute_instance" "datadog_agent" {
  name         = "speedcam-datadog"
  machine_type = var.machine_type_small
  zone         = var.zone

  depends_on = [
    google_compute_instance.rabbitmq,
    google_compute_instance.mysql
  ]

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
    # cloud-init: 컨테이너 시작 전에 Integration 설정 파일 생성
    user-data = <<-CLOUDINIT
      #cloud-config
      write_files:
        - path: /tmp/dd-confd/mysql.d/conf.yaml
          permissions: '0644'
          content: |
            init_config:
            instances:
              - host: ${google_compute_instance.mysql.network_interface[0].network_ip}
                port: 3306
                username: ${var.db_user}
                password: ${var.db_password}
                reported_hostname: speedcam-mysql
                tags:
                  - env:${var.environment}
                  - service:speedcam-mysql
        - path: /tmp/dd-confd/rabbitmq.d/conf.yaml
          permissions: '0644'
          content: |
            init_config:
            instances:
              - rabbitmq_api_url: http://${google_compute_instance.rabbitmq.network_interface[0].network_ip}:15672/api/
                rabbitmq_user: ${var.rabbitmq_user}
                rabbitmq_pass: ${var.rabbitmq_password}
                tag_families: true
                collect_node_metrics: true
                reported_hostname: speedcam-rabbitmq
                tags:
                  - env:${var.environment}
                  - service:speedcam-rabbitmq
    CLOUDINIT

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
          volumeMounts = [
            { name = "mysql-confd", mountPath = "/etc/datadog-agent/conf.d/mysql.d", readOnly = true },
            { name = "rabbitmq-confd", mountPath = "/etc/datadog-agent/conf.d/rabbitmq.d", readOnly = true },
          ]
        }]
        volumes = [
          { name = "mysql-confd", hostPath = { path = "/tmp/dd-confd/mysql.d" } },
          { name = "rabbitmq-confd", hostPath = { path = "/tmp/dd-confd/rabbitmq.d" } },
        ]
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

  allow_stopping_for_update = true
}
