# =============================================================================
# Speedcam MSA - Artifact Registry Configuration
# =============================================================================

# =============================================================================
# Artifact Registry Repository
# =============================================================================

resource "google_artifact_registry_repository" "speedcam" {
  location      = var.region
  repository_id = var.registry_name
  description   = "Speedcam MSA Docker images"
  format        = "DOCKER"
  project       = var.project_id

  labels = local.common_labels

  # Cleanup policy (optional)
  cleanup_policies {
    id     = "delete-old-images"
    action = "DELETE"

    condition {
      tag_state  = "UNTAGGED"
      older_than = "2592000s" # 30 days
    }
  }

  cleanup_policies {
    id     = "keep-recent-tagged"
    action = "KEEP"

    most_recent_versions {
      keep_count = 10
      package_name_prefixes = ["main", "ocr", "alert"]
    }
  }
}

# =============================================================================
# IAM Policy for Compute Engine to pull images
# =============================================================================

resource "google_artifact_registry_repository_iam_member" "compute_reader" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.speedcam.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${data.google_compute_default_service_account.default.email}"
}
