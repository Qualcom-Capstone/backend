# Credentials 폴더

이 폴더에는 Firebase 인증 파일이 위치합니다.
GCS (Cloud Storage)는 ADC를 사용하므로 JSON 키가 불필요합니다.

## 파일 목록

| 파일명 | 용도 | 환경변수 |
|--------|------|----------|
| `firebase-service-account.json` | FCM 푸시 알림 | `FIREBASE_CREDENTIALS` |

## 인증 방식

| 서비스 | 인증 방식 | 설정 |
|--------|----------|------|
| **GCS (Cloud Storage)** | ADC (Application Default Credentials) | GCE: 자동, 로컬: `gcloud auth application-default login` |
| **Firebase (FCM)** | Service Account JSON 키 | `FIREBASE_CREDENTIALS` 환경변수로 경로 지정 |

## 설정 방법

### Firebase Service Account
1. [Firebase Console](https://console.firebase.google.com/) 접속
2. 프로젝트 설정 → 서비스 계정 → 새 비공개 키 생성
3. 다운로드한 JSON 파일을 `firebase-service-account.json`으로 저장

### GCS (ADC)
- GCE 인스턴스: 설정 불필요 (메타데이터 서버에서 자동 인증)
- 로컬 개발: `gcloud auth application-default login` 실행

## 주의사항

- `GOOGLE_APPLICATION_CREDENTIALS` 환경변수를 설정하지 마세요 (ADC 자동 탐색 방해)
- Firebase JSON 키는 절대 Git에 커밋하지 마세요
