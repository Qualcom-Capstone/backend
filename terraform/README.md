# Speedcam MSA - Terraform 배포 가이드

GCP(Google Cloud Platform)에 Speedcam MSA 인프라를 자동으로 배포하기 위한 Terraform 구성입니다.

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                    Google Cloud Platform                         │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │    Main     │  │     OCR     │  │    Alert    │              │
│  │  (Django)   │  │   (Celery)  │  │   (Celery)  │              │
│  │  e2-medium  │  │  e2-medium  │  │   e2-small  │              │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │
│         │                │                │                      │
│         └────────────────┼────────────────┘                      │
│                          │                                       │
│              ┌───────────┴───────────┐                          │
│              │                       │                          │
│       ┌──────┴──────┐        ┌──────┴──────┐                    │
│       │  RabbitMQ   │        │    MySQL    │                    │
│       │  e2-small   │        │   e2-small  │                    │
│       │  MQTT/AMQP  │        │   4 DBs     │                    │
│       └─────────────┘        └─────────────┘                    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                   Artifact Registry                         │ │
│  │              speedcam/{main,ocr,alert}                      │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## 파일 구조

```
terraform/
├── main.tf                 # Provider 설정 및 로컬 변수
├── variables.tf            # 입력 변수 정의
├── network.tf              # 방화벽 규칙
├── artifact_registry.tf    # 컨테이너 레지스트리
├── instances_infra.tf      # RabbitMQ, MySQL 인스턴스
├── instances_services.tf   # Main, OCR, Alert 인스턴스
├── outputs.tf              # 출력 변수
├── terraform.tfvars.example # 변수 예제 파일
└── README.md               # 이 문서
```

## 사전 요구사항

1. **Terraform 설치** (v1.0 이상)
   ```bash
   # macOS
   brew install terraform

   # Linux
   wget https://releases.hashicorp.com/terraform/1.7.0/terraform_1.7.0_linux_amd64.zip
   unzip terraform_1.7.0_linux_amd64.zip
   sudo mv terraform /usr/local/bin/
   ```

2. **Google Cloud SDK 설치 및 인증**
   ```bash
   # 인증
   gcloud auth login
   gcloud auth application-default login

   # 프로젝트 설정
   gcloud config set project YOUR_PROJECT_ID
   ```

3. **필요한 API 활성화**
   ```bash
   gcloud services enable compute.googleapis.com
   gcloud services enable artifactregistry.googleapis.com
   ```

4. **Docker 이미지 빌드 및 푸시**
   ```bash
   # 프로젝트 루트에서
   make build
   make push
   ```

## 빠른 시작

### 1. 변수 파일 생성

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

### 2. 변수 파일 수정

```hcl
# terraform.tfvars
project_id = "your-actual-project-id"

# 보안을 위해 강력한 비밀번호 설정
db_password      = "your-secure-db-password"
db_root_password = "your-secure-root-password"
rabbitmq_password = "your-secure-rabbitmq-password"

# 환경 설정 (dev, staging, prod)
environment = "dev"
```

### 3. Terraform 초기화

```bash
terraform init
```

### 4. 배포 계획 확인

```bash
terraform plan
```

### 5. 인프라 배포

```bash
terraform apply
```

## 변수 설명

### 필수 변수

| 변수 | 설명 | 예시 |
|------|------|------|
| `project_id` | GCP 프로젝트 ID | `my-project-123` |

### 선택 변수 (기본값 제공)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `region` | `asia-northeast3` | GCP 리전 (서울) |
| `zone` | `asia-northeast3-a` | GCP 존 |
| `environment` | `dev` | 환경 (dev/staging/prod) |
| `db_name` | `speedcam` | 기본 데이터베이스 이름 |
| `db_user` | `sa` | 데이터베이스 사용자 |
| `db_password` | `sa` | 데이터베이스 비밀번호 |
| `rabbitmq_user` | `sa` | RabbitMQ 사용자 |
| `rabbitmq_password` | `sa` | RabbitMQ 비밀번호 |
| `machine_type_small` | `e2-small` | 작은 인스턴스 타입 |
| `machine_type_medium` | `e2-medium` | 중간 인스턴스 타입 |
| `ocr_concurrency` | `2` | OCR 워커 동시성 |
| `alert_concurrency` | `50` | Alert 워커 동시성 |
| `ocr_mock` | `true` | OCR 모킹 여부 |
| `fcm_mock` | `true` | FCM 모킹 여부 |

## 출력 값

배포 완료 후 다음 정보를 확인할 수 있습니다:

```bash
# 모든 출력 확인
terraform output

# 특정 출력 확인
terraform output api_url
terraform output swagger_url
terraform output deployment_summary
```

### 주요 출력

- `api_url` - API 기본 URL
- `swagger_url` - Swagger UI URL
- `health_url` - 헬스 체크 URL
- `rabbitmq_management_url` - RabbitMQ 관리 UI URL
- `registry_url` - Artifact Registry URL
- `deployment_summary` - 전체 배포 요약

## 환경별 배포

### 개발 환경

```hcl
# terraform.tfvars
environment = "dev"
ocr_mock    = true
fcm_mock    = true
machine_type_small  = "e2-small"
machine_type_medium = "e2-medium"
```

### 스테이징 환경

```hcl
# terraform.tfvars
environment = "staging"
ocr_mock    = false
fcm_mock    = true
machine_type_small  = "e2-small"
machine_type_medium = "e2-medium"
```

### 프로덕션 환경

```hcl
# terraform.tfvars
environment = "prod"
ocr_mock    = false
fcm_mock    = false
machine_type_small  = "e2-medium"
machine_type_medium = "e2-standard-2"
ocr_concurrency   = 4
alert_concurrency = 100
```

## Workspace 활용

여러 환경을 관리하려면 Terraform Workspace를 사용할 수 있습니다:

```bash
# Workspace 생성
terraform workspace new dev
terraform workspace new staging
terraform workspace new prod

# Workspace 전환
terraform workspace select dev

# 현재 Workspace 확인
terraform workspace show

# Workspace 목록
terraform workspace list
```

## 상태 관리

### 로컬 상태 (기본)

기본적으로 상태 파일은 로컬에 저장됩니다:
- `terraform.tfstate`
- `terraform.tfstate.backup`

### 원격 상태 (권장)

팀 협업을 위해 GCS 백엔드 사용을 권장합니다:

```hcl
# main.tf에 추가
terraform {
  backend "gcs" {
    bucket = "your-terraform-state-bucket"
    prefix = "speedcam/terraform/state"
  }
}
```

백엔드 설정 후:
```bash
terraform init -migrate-state
```

## 인프라 업데이트

### 이미지 태그 변경

```bash
terraform apply -var="image_tag=v1.2.0"
```

### 인스턴스 타입 변경

```bash
terraform apply -var="machine_type_medium=e2-standard-2"
```

### 특정 리소스만 재생성

```bash
# Main 서비스만 재생성
terraform taint google_compute_instance.main
terraform apply

# 마이그레이션만 재실행
terraform taint null_resource.run_migrations
terraform apply
```

## 인프라 삭제

```bash
# 전체 삭제 (확인 필요)
terraform destroy

# 자동 승인으로 삭제
terraform destroy -auto-approve
```

## 문제 해결

### 1. 인스턴스 시작 실패

```bash
# 인스턴스 로그 확인
gcloud compute instances get-serial-port-output speedcam-main --zone=asia-northeast3-a

# 컨테이너 로그 확인
gcloud compute ssh speedcam-main --zone=asia-northeast3-a \
  --command="docker logs \$(docker ps -q)"
```

### 2. 데이터베이스 연결 실패

```bash
# MySQL 상태 확인
gcloud compute ssh speedcam-mysql --zone=asia-northeast3-a \
  --command="docker exec \$(docker ps -q) mysqladmin -u root -p status"
```

### 3. RabbitMQ 연결 실패

```bash
# RabbitMQ 상태 확인
gcloud compute ssh speedcam-rabbitmq --zone=asia-northeast3-a \
  --command="docker exec \$(docker ps -q) rabbitmqctl status"
```

### 4. Terraform 상태 문제

```bash
# 상태 새로고침
terraform refresh

# 상태에서 리소스 제거 (실제 리소스는 유지)
terraform state rm google_compute_instance.main

# 기존 리소스 가져오기
terraform import google_compute_instance.main speedcam-main
```

## 비용 최적화

### 예상 월간 비용 (asia-northeast3 기준)

| 리소스 | 타입 | 예상 비용 |
|--------|------|----------|
| Main | e2-medium | ~$25 |
| OCR | e2-medium | ~$25 |
| Alert | e2-small | ~$13 |
| RabbitMQ | e2-small | ~$13 |
| MySQL | e2-small + SSD | ~$18 |
| **총계** | | **~$94/월** |

### 비용 절감 팁

1. **Preemptible VM 사용** (개발 환경)
   ```hcl
   scheduling {
     preemptible = true
   }
   ```

2. **자동 시작/중지 스케줄링**
   - Cloud Scheduler로 업무 시간 외 인스턴스 중지

3. **Committed Use Discounts**
   - 1년/3년 약정으로 최대 57% 할인

## 보안 고려사항

1. **비밀번호 관리**
   - Secret Manager 사용 권장
   - terraform.tfvars를 .gitignore에 추가

2. **네트워크 보안**
   - 프로덕션에서는 외부 IP 제거
   - VPN 또는 IAP 터널 사용

3. **서비스 계정**
   - 최소 권한 원칙 적용
   - 전용 서비스 계정 생성

## 참고 자료

- [Terraform GCP Provider 문서](https://registry.terraform.io/providers/hashicorp/google/latest/docs)
- [GCP Container-Optimized OS](https://cloud.google.com/container-optimized-os/docs)
- [GCP 가격 계산기](https://cloud.google.com/products/calculator)
