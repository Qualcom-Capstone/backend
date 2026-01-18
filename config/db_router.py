"""
MSA Database Router

각 서비스(앱)별로 독립적인 DB를 사용하도록 라우팅합니다.
- vehicles 앱 → vehicles DB
- detections 앱 → detections DB
- notifications 앱 → notifications DB
- 기타 (auth, admin 등) → default DB
"""


class MSADatabaseRouter:
    """
    MSA 환경을 위한 Database Router
    각 앱을 해당 데이터베이스로 라우팅합니다.
    """
    
    # 앱별 DB 매핑
    APP_DB_MAPPING = {
        'vehicles': 'vehicles_db',
        'detections': 'detections_db',
        'notifications': 'notifications_db',
    }
    
    def _get_db_for_app(self, app_label):
        """앱 라벨에 해당하는 DB 반환"""
        return self.APP_DB_MAPPING.get(app_label, 'default')
    
    def db_for_read(self, model, **hints):
        """
        읽기 작업을 위한 DB 선택
        """
        return self._get_db_for_app(model._meta.app_label)
    
    def db_for_write(self, model, **hints):
        """
        쓰기 작업을 위한 DB 선택
        """
        return self._get_db_for_app(model._meta.app_label)
    
    def allow_relation(self, obj1, obj2, **hints):
        """
        두 객체 간의 관계 허용 여부
        
        MSA에서는 서비스 간 직접 FK 관계를 권장하지 않지만,
        현재 구조에서는 Detection → Vehicle 관계가 있으므로 허용.
        향후 이벤트 기반 참조로 전환 권장.
        """
        # 같은 DB에 있으면 항상 허용
        db1 = self._get_db_for_app(obj1._meta.app_label)
        db2 = self._get_db_for_app(obj2._meta.app_label)
        
        if db1 == db2:
            return True
        
        # vehicles-detections 관계 허용 (FK)
        apps = {obj1._meta.app_label, obj2._meta.app_label}
        if apps == {'vehicles', 'detections'}:
            return True
        
        # detections-notifications 관계 허용 (FK)
        if apps == {'detections', 'notifications'}:
            return True
        
        return None  # 다른 경우는 기본 라우터에 위임
    
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        마이그레이션 실행 DB 결정
        """
        target_db = self._get_db_for_app(app_label)
        
        # 해당 앱의 타겟 DB와 현재 DB가 일치하면 마이그레이션 허용
        if target_db == db:
            return True
        
        # default DB에는 Django 기본 앱들만 마이그레이션
        if db == 'default':
            return app_label not in self.APP_DB_MAPPING
        
        return False

