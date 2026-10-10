-- ytweb 데이터베이스 안에서 실행한다(초기화: 슈퍼유저, 데모 초기화: ytweb_owner). 여러 번 실행해도 결과가 같다.
-- 앱 역할(ytweb_app)은 DDL 불가, 테이블 DML 과 시퀀스 사용만 가능하다. 감사 로그의 UPDATE/DELETE 회수는
-- 백엔드 마이그레이션 0001 이 하고, audit-guard.sql 이 복원 뒤에 다시 확인한다.
ALTER SCHEMA public OWNER TO ytweb_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO ytweb_app;

ALTER DEFAULT PRIVILEGES FOR ROLE ytweb_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ytweb_app;
ALTER DEFAULT PRIVILEGES FOR ROLE ytweb_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO ytweb_app;
