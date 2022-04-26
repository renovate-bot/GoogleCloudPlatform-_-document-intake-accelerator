#Creating a cloud run service

resource "google_cloud_run_service" "queue-run" {
  name     = "queue-cloudrun"
  location = var.region

  template {
    spec {
      containers {
        image = var.cloud_run_image_path   #Image to connect pubsub to cloud run to processtask API and fetch data from firestore
        ports{
            container_port=8000
        }
        env {
          name = "t"  #thresold value for comparison with the number of uploaded docs in firesotre collection
          value = "10"
        }
       
      }
      service_account_name = module.cloud-run-service-account.email
    }
  }
  traffic {
    percent         = 100
    latest_revision = true
    }
}

#Displaying the cloudrun endpoint

output "cloud_run" {
    value = google_cloud_run_service.queue-run.status[0].url
}
