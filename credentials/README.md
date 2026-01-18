# Credentials 폴더

이 폴더에는 GCP 및 Firebase 인증 관련 파일들이 위치합니다.

## 파일 목록

| 파일명 | 용도 | 환경변수 |
|--------|------|----------|
| `firebase-service-account.json` | FCM 푸시 알림 | `FIREBASE_CREDENTIALS` |
| `gcp-cloud-storage.json` | GCS 이미지 저장소 | `GOOGLE_APPLICATION_CREDENTIALS` |

## 설정 방법

### 1. Firebase Service Account
1. [Firebase Console](https://console.firebase.google.com/) 접속
2. 프로젝트 설정 → 서비스 계정 → 새 비공개 키 생성
3. 다운로드한 JSON 파일을 `firebase-service-account.json`으로 저장

### 2. GCP Service Account (Cloud Storage)
1. [GCP Console](https://console.cloud.google.com/) 접속
2. IAM 및 관리자 → 서비스 계정 → 키 생성
3. 필요한 역할: `Storage Object Viewer`, `Storage Object Creator`
4. 다운로드한 JSON 파일을 `gcp-cloud-storage.json`으로 저장

## 주의사항

- ⚠️ **실제 인증 파일은 절대 Git에 커밋하지 마세요**
- Docker 환경에서는 볼륨 마운트 또는 Secret Manager 사용 권장
