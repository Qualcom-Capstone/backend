-- MSA Database Initialization Script
-- 각 서비스별 독립 데이터베이스 생성

-- Default DB (Django 기본 - auth, admin, sessions)
CREATE DATABASE IF NOT EXISTS speedcam CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Vehicles Service DB
CREATE DATABASE IF NOT EXISTS speedcam_vehicles CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Detections Service DB
CREATE DATABASE IF NOT EXISTS speedcam_detections CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Notifications Service DB  
CREATE DATABASE IF NOT EXISTS speedcam_notifications CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Grant privileges to user
GRANT ALL PRIVILEGES ON speedcam.* TO 'sa'@'%';
GRANT ALL PRIVILEGES ON speedcam_vehicles.* TO 'sa'@'%';
GRANT ALL PRIVILEGES ON speedcam_detections.* TO 'sa'@'%';
GRANT ALL PRIVILEGES ON speedcam_notifications.* TO 'sa'@'%';

FLUSH PRIVILEGES;

