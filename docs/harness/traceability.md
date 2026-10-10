# 요구사항 추적 매트릭스 (Requirements Traceability Matrix)

> 2~4단계 산출물(`02_planning.md`, `02_risk_assessment.md`, `DESIGN.md`, `04_ux_design.md`)을 파싱해 생성(수작업 전사 오류 방지). 5단계 이후 구현 상태·테스트 컬럼을 갱신한다. 새 ID는 임의로 추가하지 않는다(규칙 H).

| ID | 유형 | 요구사항/기능 (출처 문서 §) | 설계 매핑 (TRD §) | 작업 단위 (unit-n) | 구현 상태 | 단위테스트 (TC-ID) | 통합테스트 (IT-ID) | 전체테스트 (UAT-ID) | 비고 |
|----|------|------------------------------|---------------------|----------------------|------------|----------------------|------------------------|---------------------------|------|
| FR-001 | FR | 제목 후보 파일 candidates/{video_id}.json 읽기와 스키마 검증(필드: video_id, current_title, topic, summary, candidates[{title, evidence}], source, 선택 descri (02 §4-1) | 4-3 EVT-201, 6-1 SEC-011 | WU-3 | Done | TC-300, TC-301, TC-302, TC-303, TC-304, TC-308, TC-311, TC-312, TC-353 |  |  |  |
| FR-002 | FR | 제목 규칙 검증기: 길이(핵심어 앞 20자, 권장 40자, 하드 상한 100자, 유니코드 문자 수 기준), < > 불가, 차단 유형(공포 조장·의료 효능 단정·금융 수익/원금 보장·공공기관/뉴스 사칭 오인·근거 없는 최상급/100% 단정), 경고 유형 (02 §4-1) | 1-1 validator.py, 9 WU-3, 7장 제목 규칙 → `04` 및 02 §4-1 | WU-3 | Done | TC-007, TC-037, TC-320, TC-321, TC-322, TC-324, TC-325, TC-326, TC-327, TC-328, TC-336, TC-337, TC-430, TC-431, TC-441, TC-933, TC-987 |  |  |  |
| FR-003 | FR | 금칙어 사전 config/banned_terms.yaml(유형 단위 관리, 사용자 수정 가능, 예시 목록이 아닌 유형 기반). 매칭은 공백·특수문자·전각/반각을 정규화한 뒤 수행하고 우회 표기(예: 띄어쓰기·기호 삽입) 테스트를 포함한다 (02 §4-1) | 4-3 EVT-204, 6-2 SEC-017 | WU-3 | Done | TC-038, TC-039, TC-316, TC-318, TC-322, TC-323, TC-338, TC-339, TC-360 |  |  |  |
| FR-004 | FR | 제목-내용 일치 점검: 영상 설명과 사용자 제공 요약 기반 핵심어 일치율 계산, 후보마다 일치 근거 문장 기록. 영상 설명은 후보 파일의 선택 필드 description_excerpt 또는 DB videos 테이블(WU-2가 채움)에서 읽고, 둘 다  (02 §4-1) | 4-3 EVT-201(description_excerpt), 3-1 videos | WU-3 | Done | TC-321, TC-322, TC-332, TC-333, TC-334, TC-335, TC-341, TC-355, TC-356 |  |  |  |
| FR-005 | FR | 검증 결과 리포트: 통과/경고/차단 + 사유(+ 건강·금융 주제는 경고도 차단) (02 §4-1) | 4-1 EVT-003, `04_ux_design.md` SCR-002 | WU-3 | Done | TC-321, TC-329, TC-343, TC-344, TC-346, TC-347, TC-434, TC-435, TC-437, TC-446, TC-502, TC-907 |  |  |  |
| FR-006 | FR | 읽기 전용 조회: videos.list로 snippet 조회(최대 50개 배치), 채널 영상 목록 조회 (02 §4-1) | 4-2 EVT-101~103 | WU-2 | Done | TC-220, TC-221, TC-222, TC-223, TC-224, TC-225, TC-226, TC-227, TC-228, TC-229, TC-230, TC-231, TC-232, TC-233, TC-235, TC-236, TC-259, TC-261, TC-262, TC-264, TC-268, TC-271, TC-275, TC-276, TC-289 |  |  |  |
| FR-007 | FR | 성과 지표 수집: Analytics API(노출수·CTR·시청시간) + API로 얻지 못할 때 Studio 내보내기 CSV 가져오기 (02 §4-1) | 4-2 EVT-105, 4-3 EVT-203 | WU-2, WU-6 | Done | TC-240, TC-241, TC-242, TC-243, TC-244, TC-245, TC-246, TC-247, TC-264, TC-267, TC-268, TC-273, TC-274, TC-277, TC-278, TC-279, TC-280, TC-290, TC-406, TC-600, TC-601, TC-603, TC-604, TC-608, TC-610, TC-617, TC-620, TC-624, TC-625, TC-626, TC-627, TC-640, TC-660, TC-661, TC-667, TC-668, TC-669, TC-678, TC-683, TC-684, TC-687 |  |  | Analytics API 지표 가용성 [확인 필요]. 불가 시 CSV 경로가 필수 |
| FR-008 | FR | dry-run 수정(기본 모드): 실제 호출 없이 "무엇이 어떻게 바뀔지" diff 출력, 대상 영상이 공식 A/B 진행 중인지 사용자에게 확인하라는 문구 출력 (02 §4-1) | 4-1 EVT-004, 5-2 | WU-4 | Done | TC-432, TC-439, TC-500, TC-911, TC-950 |  |  |  |
| FR-009 | FR | 수정 전 현재 snippet 전체 백업과, "이전 값 보존 + 제목만 변경" 요청 본문 구성 (02 §4-1) | 5-2 9단계, 3-1 title_changes | WU-4 | Done | TC-426, TC-463, TC-570, TC-572, TC-929 |  |  |  |
| FR-010 | FR | 모든 변경(시도 포함) 이력 DB 기록: 이전 제목, 새 제목, 시각, 사유, 승인자, 결과 (02 §4-1) | 3-1 title_changes | WU-4 | Done | TC-463, TC-482, TC-645 |  |  |  |
| FR-011 | FR | 롤백 명령: 단일 명령으로 이전 제목 복원(복원도 이력에 기록) (02 §4-1) | 4-1 EVT-007 | WU-4 | Done | TC-483, TC-487, TC-488, TC-489, TC-491, TC-493, TC-494, TC-495, TC-496, TC-497, TC-520, TC-523, TC-684, TC-685, TC-913, TC-914, TC-915, TC-918, TC-920, TC-921, TC-984, TC-985, TC-986 |  |  |  |
| FR-012 | FR | 실제 수정 모드: (1)명시적 CLI 플래그, (2)영상별 사람 승인 파일, (3)설정 enable_live=true 세 조건 모두 충족 시에만 활성화. 적용 전 "무엇을 어떤 영상에 적용하는지" 요약 출력, 해당 영상의 변경 전 지표 스냅샷 존재를  (02 §4-1) | 5-2 | WU-5 | Done | TC-570, TC-571, TC-574, TC-634, TC-664, TC-952, TC-954, TC-981 |  |  |  |
| FR-013 | FR | 영상별 사람 승인 파일의 형식 정의, 생성·검증·만료 처리 (02 §4-1) | 4-1 EVT-005, 4-3 EVT-202, 6-2 SEC-014 | WU-5 | Done | TC-464, TC-530, TC-532, TC-541, TC-549, TC-554, TC-555, TC-952, TC-970, TC-975, TC-976, TC-981 |  |  |  |
| FR-014 | FR | 교체 제한 검사: 동일 영상 최소 72시간 간격, 영상당 총 변경 횟수 상한, 최소 노출 수 충족 전 재변경 금지 (02 §4-1) | 5-3 cadence, 5-2 5단계 | WU-4 | Done | TC-400, TC-401, TC-402, TC-403, TC-404, TC-405, TC-406, TC-407, TC-409, TC-411, TC-412, TC-413, TC-414, TC-417, TC-419, TC-444, TC-505, TC-650, TC-665, TC-972 |  |  |  |
| FR-015 | FR | 쿼터 사용량 기록(quota_usage)과 일일 상한 검사(초과 시 즉시 중단), 하루 경계는 태평양 시간 기준 (02 §4-1) | 3-1 quota_usage, 5-3 quota, ADR-008 | WU-2 | Done | TC-200, TC-201, TC-202, TC-204, TC-205, TC-206, TC-207, TC-208, TC-209, TC-212, TC-213, TC-214, TC-257, TC-258, TC-275, TC-283, TC-579 |  |  |  |
| FR-016 | FR | OAuth 인증(설치형 앱 방식): 최소 scope, 토큰 로컬 저장(권한 제한), 만료·재인증 처리 (02 §4-1) | 4-1 EVT-001, ADR-004 | WU-1 | Done | TC-080, TC-084, TC-087, TC-089, TC-090, TC-091, TC-100, TC-102, TC-251, TC-286, TC-287 |  |  |  |
| FR-017 | FR | CLI: --dry-run 기본값, --help, 서브커맨드(검증, 계획, 적용, 롤백, 리포트, 인증, 데이터 정리(purge)) (02 §4-1) | 4-1 | WU-0 | Done | TC-002, TC-055, TC-057, TC-065, TC-072, TC-074, TC-513 |  |  |  |
| FR-018 | FR | 성과 비교 리포트: 변경 전후 노출·CTR·시청시간 비교 + 순차 비교의 신뢰도 한계 문구 상시 표기 (02 §4-1) | 4-1 EVT-008 | WU-6 | Done | TC-630, TC-631, TC-632, TC-633, TC-634, TC-637, TC-638, TC-639, TC-640, TC-641, TC-642, TC-643, TC-645, TC-646, TC-647, TC-648, TC-649, TC-651, TC-652, TC-653, TC-662, TC-663, TC-665, TC-671, TC-672, TC-677, TC-686 |  |  | Analytics API 지표 가용성 [확인 필요]. 불가 시 CSV 경로가 필수 |
| FR-019 | FR | 순차 교체 모드(공식 A/B 불가 영상용): 허용하되 기본 비활성, 활성 시에도 Shorts·비공개·아동용·예약 라이브·프리미어는 제외 (02 §4-1) | 5-3 sequential_mode, 3-2 | WU-4 | Done | TC-447, TC-449, TC-509, TC-635, TC-650 |  |  |  |
| FR-020 | FR | 실행 로그(run_logs): 실행 단위 기록, 토큰·키 비노출 (02 §4-1) | 3-1 run_logs, 5-1 NFR-011 | WU-0 | Done | TC-027, TC-062, TC-071, TC-073, TC-079 |  |  |  |
| NFR-001 | NFR | 지원 환경: Windows 10/11 + PowerShell 5.1 이상 + Python 3.12 (02 §6-1) | 5-1 | WU-0 | Done |  |  |  |  |
| NFR-002 | NFR | 인코딩: 모든 파일 UTF-8, 한글 제목·경로·콘솔 출력 정상 (02 §6-1) | 5-1 | WU-0 | Done | TC-013, TC-040, TC-043, TC-053, TC-301, TC-324, TC-325, TC-605, TC-606, TC-679, TC-688 |  |  |  |
| NFR-003 | NFR | 쿼터 통제: 일일 상한 기본 = 기본 쿼터의 60% 이하(설정값), 하루 경계 태평양 시간 (02 §6-1) | 5-1, 5-3 | WU-2 | Done | TC-001, TC-029, TC-201, TC-203, TC-207, TC-208, TC-209, TC-210, TC-250, TC-257, TC-283, TC-284, TC-285, TC-416 |  |  |  |
| NFR-004 | NFR | 재시도: 오류 시 최대 2회(지수 백오프), 이후 중단·기록 (02 §6-1) | 4-2 | WU-0 | Done | TC-015, TC-019, TC-020, TC-252, TC-253, TC-254, TC-255, TC-589, TC-934 |  |  |  |
| NFR-005 | NFR | 검증 성능: 후보 100건 검증 5초 이내(네트워크 제외, 로컬, 가정) (02 §6-1) | 5-1, 9 WU-3 | WU-3 | Done | TC-342 |  |  |  |
| NFR-006 | NFR | 테스트 품질: 제목 검증기·요청 본문 구성 모듈의 줄 커버리지 90% 이상(가정) (02 §6-1) | 5-1, 9 | WU-3, WU-4 | Done |  |  |  |  |
| NFR-007 | NFR | 초보자 사용성: 모든 오류 메시지는 한국어이며 "다음에 할 일"을 함께 안내 (02 §6-1) | 4-1, `04_ux_design.md` | WU-0 | Done | TC-006, TC-028, TC-033, TC-036, TC-046, TC-052, TC-060, TC-061, TC-063, TC-069, TC-075, TC-079, TC-086, TC-088, TC-092, TC-101, TC-202, TC-213, TC-221, TC-231, TC-244, TC-251, TC-256, TC-261, TC-265, TC-268, TC-270, TC-279, TC-282, TC-287, TC-302, TC-303, TC-308, TC-312, TC-313, TC-319, TC-350, TC-351, TC-353, TC-417, TC-420, TC-428, TC-454, TC-469, TC-470, TC-477, TC-494, TC-503, TC-522, TC-526, TC-540, TC-549, TC-557, TC-558, TC-615, TC-628, TC-668, TC-670, TC-673, TC-955, TC-958, TC-962 |  |  |  |
| NFR-008 | NFR | 감사 가능성: 모든 쓰기 시도·결과·승인자를 DB에 기록, 실행 로그 보관 365일(가정, 설정값) (02 §6-1) | 3-1, 5-1 | WU-0 | Done | TC-032, TC-073, TC-462, TC-463, TC-465, TC-473, TC-475, TC-480, TC-481, TC-497, TC-556, TC-591, TC-592, TC-593, TC-597, TC-598, TC-902, TC-905, TC-906, TC-908, TC-916, TC-919, TC-959, TC-977 |  |  |  |
| NFR-009 | NFR | 데이터 최소 보관: 백업 snippet은 변경 이력과 함께 보관하고 보관 기간·삭제 명령을 제공 (02 §6-1) | 3-4 | WU-0 | Done | TC-066, TC-068, TC-229 |  |  |  |
| NFR-010 | NFR | 복구 목표: RPO ≤ 24시간, RTO ≤ 30분(가정). 쓰기 직전마다 DB 사본(data/backups/)을 만들고, 복구는 사본 파일 복사로 한다 (DESIGN §5-1) | 5-1, 7 | WU-0 | Done | TC-025, TC-490, TC-900, TC-901 |  |  |  |
| NFR-011 | NFR | 관측성: 실행 로그는 사람이 읽는 한국어 한 줄 + run_id, data/logs/ytitle.log(회전 5MB×10). 토큰·키 마스킹(SEC-008) (DESIGN §5-1) | 5-1, 7 | WU-0 | Done | TC-012, TC-014 |  |  |  |
| POL-001 | POL | 건강·금융 주제는 엄격 모드(경고도 차단). topic 미지정 시, 또는 제목·요약에 건강·금융 키워드가 감지되면 topic 값과 무관하게 엄격 모드 (02 §7-1) | 4-3 EVT-201 topic, 3-2 | WU-3 | Done | TC-329, TC-330, TC-331, TC-354, TC-434, TC-502, TC-961, TC-973, TC-980 |  |  | 규칙 I 보수 적용(DEC-012) |
| POL-002 | POL | 검증 리포트·dry-run 출력·성과 리포트에 "이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다" 문구를 표기 (02 §7-1) | `04_ux_design.md` 면책 문구 규칙 | WU-3, WU-4, WU-6 | Done | TC-049, TC-055, TC-275, TC-344, TC-500, TC-649, TC-662, TC-663 |  |  | 규칙 I 보수 적용(DEC-012) |
| POL-003 | POL | 공식 A/B 불가 영상군(Shorts, 예약 라이브, 프리미어, 비공개, 아동용)에는 공식 A/B가 가능하다고 가정하지 않으며, 순차 교체 모드에서도 기본 제외 (02 §7-1) | 5-3 sequential_mode, 8-4 | WU-4 | Done | TC-447, TC-448, TC-449, TC-507, TC-509 |  |  |  |
| POL-004 | POL | 후보 파일의 source(예: human, ai-assisted) 필드를 필수 기록해, 향후 AI 관련 고지 의무가 확인되면 대응 가능하게 한다 (02 §7-1) | 4-3 EVT-201 source | WU-3 | Done | TC-314 |  |  |  |
| SEC-001 | SEC | 사람 승인 없이 videos.update 호출 금지. 기본값은 항상 dry-run (02 §7-1) | 5-2, 6-1 | WU-0, WU-5 | Done | TC-004, TC-005, TC-042, TC-047, TC-048, TC-058, TC-060, TC-064, TC-067, TC-098, TC-262, TC-263, TC-286, TC-359, TC-432, TC-434, TC-450, TC-451, TC-452, TC-453, TC-464, TC-465, TC-466, TC-476, TC-498, TC-501, TC-502, TC-504, TC-521, TC-570, TC-571, TC-574, TC-575, TC-576, TC-577, TC-578, TC-582, TC-599, TC-653, TC-677, TC-682, TC-906, TC-911, TC-912, TC-915, TC-917, TC-922, TC-923, TC-928, TC-950, TC-951, TC-955, TC-956, TC-960, TC-961 |  |  |  |
| SEC-002 | SEC | 일일 쿼터 상한을 설정으로 두고(기본 60% 이하) 초과 시 즉시 중단 (02 §7-1) | 5-2, 6-1 | WU-2 | Done | TC-200, TC-201, TC-202, TC-203, TC-204, TC-206, TC-207, TC-212, TC-214, TC-220, TC-223, TC-224, TC-226, TC-235, TC-236, TC-240, TC-241, TC-243, TC-247, TC-250, TC-252, TC-257, TC-258, TC-260, TC-283, TC-284, TC-445, TC-506, TC-574, TC-579, TC-588, TC-595, TC-904, TC-966 |  |  |  |
| SEC-003 | SEC | 재시도 최대 2회(지수 백오프), 무한 재시도 금지 (02 §7-1) | 4-2, 6-1 | WU-0 | Done | TC-015, TC-016, TC-017, TC-018, TC-250, TC-251, TC-252, TC-253, TC-254, TC-255, TC-266, TC-587, TC-588, TC-589, TC-590, TC-934 |  |  |  |
| SEC-004 | SEC | 교체 주기: 동일 영상 최소 72시간, 영상당 총 변경 횟수 상한(기본 3회), 최소 노출 수 충족(기본 1,000회) 전 재변경 금지. 모두 설정값 (02 §7-1) | 5-2, 6-1 | WU-4 | Done | TC-001, TC-400, TC-403, TC-405, TC-411, TC-419, TC-444, TC-467, TC-505, TC-574, TC-972 |  |  |  |
| SEC-005 | SEC | 수정은 항상 snippet 전체 보존 + 제목만 변경, 수정 전 원본 snippet 백업 필수 (02 §7-1) | 5-2, 6-1 | WU-4 | Done | TC-426, TC-427, TC-428, TC-429, TC-440, TC-455, TC-463, TC-483, TC-485, TC-524, TC-572, TC-573, TC-929, TC-930, TC-931, TC-932, TC-933, TC-987 |  |  |  |
| SEC-006 | SEC | 모든 변경은 DB 기록, 단일 명령 롤백 (02 §7-1) | 3-1, 6-1 | WU-4 | Done | TC-022, TC-023, TC-068, TC-348, TC-419, TC-460, TC-463, TC-471, TC-473, TC-474, TC-475, TC-478, TC-483, TC-490, TC-496, TC-587, TC-591, TC-643, TC-644, TC-900, TC-913, TC-918, TC-921, TC-937, TC-958 |  |  |  |
| SEC-007 | SEC | 금지: 비공식 크롤링, 브라우저 자동화로 Studio 조작, 다중 Cloud 프로젝트로 쿼터 확장, 공식 A/B 가정(Shorts·비공개·아동용) — 구현 단위가 아니라 9단계 점검 항목 (02 §7-1) | 6-1 (9단계 점검) | 9단계 점검 항목 | Not Started | TC-262, TC-359, TC-451, TC-629, TC-653, TC-682, TC-922, TC-923, TC-925 |  |  | 구현 단위 아님 — 9단계가 금지 사항 부재를 점검 |
| SEC-008 | SEC | 토큰·키·credentials는 .env/별도 파일, 로그·예외 메시지 비노출, .gitignore 등록 (02 §7-1) | 6-1 | WU-0, WU-1 | Done | TC-010, TC-011, TC-013, TC-051, TC-061, TC-078, TC-082, TC-083, TC-085, TC-090, TC-097, TC-256, TC-265, TC-561, TC-596, TC-935 |  |  |  |
| SEC-009 | SEC | 실제 호출 직전에 서버의 현재 제목을 재조회해 백업 시점과 다르면 중단(사람이 Studio에서 바꾼 제목 보호) (02 §7-1) | 5-2, 6-1 | WU-4 | Done | TC-424, TC-433, TC-440, TC-486, TC-491, TC-499, TC-512, TC-524, TC-573, TC-574, TC-915 |  |  |  |
| SEC-010 | SEC | 수정 후 videos.list로 재조회해 제목 반영과 설명·태그·카테고리 보존을 검증·기록 (02 §7-1) | 5-2, 6-1 | WU-5 | Done | TC-471, TC-472, TC-570, TC-582, TC-583, TC-584, TC-585, TC-586, TC-592, TC-685, TC-920, TC-939, TC-957, TC-985 |  |  |  |
| SEC-011 | SEC | 후보 JSON은 신뢰할 수 없는 입력: 스키마·video_id 형식·크기 검증(경로 조작 방지) (02 §7-1) | 6-1 | WU-3 | Done | TC-271, TC-304, TC-305, TC-306, TC-307, TC-309, TC-310, TC-311, TC-352, TC-546 |  |  |  |
| SEC-012 | SEC | 첫 실제 호출은 사용자가 알려준 비공개 테스트 영상만 가능하도록 영상 ID 허용 목록(allowlist) (02 §7-1) | 5-2, 5-3 | WU-5 | Done | TC-005, TC-009, TC-449, TC-574, TC-577, TC-912, TC-915 |  |  |  |
| SEC-013 | SEC | 신규 의존성은 공식 레지스트리(PyPI)에 실존하는지·라이선스를 확인하고 버전을 고정한다(패키지 환각 방지) (02 §7-1) | 2-1 | WU-0 | Done |  |  |  |  |
| SEC-014 | SEC | 승인 파일은 plan_hash(영상 ID·후보 ID·새 제목·이전 제목·현재 snippet 해시)에 바인딩되고, 만료(기본 24시간)되며, 한 번 사용하면 used=true로 재사용을 막는다 (DESIGN §6-2) | 6-2 | WU-5 | Done | TC-421, TC-422, TC-423, TC-424, TC-425, TC-433, TC-466, TC-484, TC-499, TC-512, TC-530, TC-531, TC-532, TC-533, TC-534, TC-535, TC-536, TC-537, TC-538, TC-539, TC-540, TC-541, TC-542, TC-543, TC-544, TC-545, TC-546, TC-547, TC-548, TC-550, TC-551, TC-552, TC-553, TC-554, TC-555, TC-557, TC-560, TC-561, TC-570, TC-574, TC-902, TC-903, TC-909, TC-910, TC-938, TC-970, TC-971, TC-979, TC-981 |  |  |  |
| SEC-015 | SEC | 읽기 토큰과 쓰기 토큰을 분리 저장하고, 쓰기 토큰은 apply/rollback 실행 순간에만 로드한다. auth --revoke로 로컬 삭제 (DESIGN §6-2) | 6-2 | WU-1 | Done | TC-050, TC-080, TC-081, TC-093, TC-094, TC-095, TC-098, TC-286, TC-531, TC-571, TC-588, TC-596, TC-599, TC-913, TC-924, TC-926, TC-927 |  |  |  |
| SEC-016 | SEC | 안전한 파싱: yaml.safe_load만 사용, JSON/CSV 크기 상한, CSV는 값을 실행·평가하지 않고 숫자·문자열로만 읽음 (DESIGN §6-2) | 6-2 | WU-0, WU-3, WU-6 | Done | TC-008, TC-310, TC-318, TC-360, TC-551, TC-552, TC-607, TC-609, TC-611, TC-612, TC-613, TC-614, TC-618, TC-621, TC-622, TC-623, TC-629, TC-639, TC-641, TC-673, TC-675, TC-678, TC-680, TC-686, TC-687, TC-688 |  |  |  |
| SEC-017 | SEC | 검증 때 사용한 금칙어 사전의 해시를 후보 검증 기록에 저장하고, 사전이 바뀐 사실을 리포트에 표시 (DESIGN §6-2) | 6-2 | WU-3 | Done | TC-317, TC-340, TC-345, TC-507, TC-508 |  |  |  |
| SEC-018 | SEC | 모든 SQL은 파라미터 바인딩(문자열 결합 금지). 제목·설명 등 외부 문자열은 값으로만 전달 (DESIGN §6-2) | 6-2 | WU-0 | Done | TC-024, TC-211, TC-227, TC-234, TC-418, TC-468, TC-624, TC-651, TC-676 |  |  |  |
| SEC-019 | SEC | 화면·로그에 출력하는 외부 문자열(제목·설명·사유)은 제어 문자(ANSI 이스케이프 포함)를 제거/이스케이프한다 (DESIGN §6-2) | 6-2 | WU-0 | Done | TC-034, TC-035, TC-045, TC-234, TC-281, TC-358, TC-430, TC-510, TC-525, TC-556, TC-611, TC-616, TC-675, TC-916, TC-936, TC-963, TC-977, TC-980 |  |  |  |
| SEC-020 | SEC | apply와 rollback은 1회 실행에 영상 1건만 처리하고(일괄 적용 없음), 하루 live 적용 건수 상한(max_live_changes_per_day, 기본 3)을 둔다 (DESIGN §6-2) | 5-2, 5-3, 6-2 | WU-5 | Done | TC-408, TC-415, TC-456, TC-467, TC-487, TC-574, TC-580, TC-581, TC-953, TC-965 |  |  |  |
| EVT-001 | EVT | CLI auth 설치형 앱 OAuth. 읽기·쓰기 토큰을 분리 저장(ADR-004). --revoke는 로컬 토큰 삭제와 구글 계정에서의 앱 접근 제거 안내(계정 회수 절차) (DESIGN §4-1) | DESIGN 4-1 | WU-1 | Done | TC-096, TC-097, TC-099 |  |  |  |
| EVT-002 | EVT | CLI fetch 영상 목록·snippet 조회(읽기 전용 API), 지표 수집 (DESIGN §4-1) | DESIGN 4-1 | WU-2 | Done | TC-270, TC-272, TC-288, TC-661 |  |  |  |
| EVT-003 | EVT | CLI validate 후보 검증, 리포트 출력 (DESIGN §4-1) | DESIGN 4-1 | WU-3 | Done | TC-315, TC-344, TC-349 |  |  |  |
| EVT-004 | EVT | CLI plan dry-run diff. 쓰기 API·읽기 API 호출 없음(마지막 fetch로 저장된 videos.snippet_json 사용, 저장 시각이 24시간보다 오래되면 fetch를 다시 하라고 경고). 계획 해시 plan_hash = SH (DESIGN §4-1) | DESIGN 4-1 | WU-4 | Done | TC-421, TC-422, TC-432, TC-438, TC-442, TC-443, TC-500, TC-501, TC-503, TC-504, TC-507, TC-964, TC-980 |  |  |  |
| EVT-005 | EVT | CLI approve 사람의 승인 파일 생성(계획 해시 바인딩, 만료 포함) (DESIGN §4-1) | DESIGN 4-1 | WU-5 | Done | TC-970, TC-978 |  |  |  |
| EVT-006 | EVT | CLI apply 후보 1건씩만 처리. 5-2의 안전 게이트를 모두 통과해야 실행. 기본(옵션 없음)은 dry-run (DESIGN §4-1) | DESIGN 4-1 | WU-5 | Done | TC-950, TC-951, TC-953, TC-954 |  |  |  |
| EVT-007 | EVT | CLI rollback 이전 제목 복원(복원도 이력 기록). 게이트: --live + enable_live + 영상 ID 직접 입력 확인 + 허용 목록 (DESIGN §4-1) | DESIGN 4-1 | WU-4, WU-5 | Done | TC-498, TC-520, TC-522, TC-683, TC-684, TC-913, TC-983, TC-984 |  |  |  |
| EVT-008 | EVT | CLI report 변경 전후 비교 리포트와 CSV 가져오기 (DESIGN §4-1) | DESIGN 4-1 | WU-6 | Done | TC-623, TC-660, TC-661, TC-674, TC-684 |  |  |  |
| EVT-009 | EVT | CLI purge 오래된 이력 삭제(자동 DB 사본, 확인 필요) (DESIGN §4-1) | DESIGN 4-1 | WU-0 | Done |  |  |  |  |
| EVT-101 | EVT | channels.list (mine=true, part=contentDetails) — 업로드 재생목록 ID 획득 (DESIGN §4-2) | DESIGN 4-2 | WU-2 | Done |  |  |  |  |
| EVT-102 | EVT | playlistItems.list — 영상 ID 목록(50개씩 페이지) (DESIGN §4-2) | DESIGN 4-2 | WU-2 | Done |  |  |  |  |
| EVT-103 | EVT | videos.list (part=snippet,status,contentDetails, 최대 50 ID) — snippet 전체·상태 조회 (DESIGN §4-2) | DESIGN 4-2 | WU-2 | Done |  |  |  |  |
| EVT-104 | EVT | videos.update (part=snippet) — 제목 변경(전체 snippet 보존 본문) (DESIGN §4-2) | DESIGN 4-2 | WU-5 | Done |  |  |  |  |
| EVT-105 | EVT | Analytics reports.query — 영상별 지표 (DESIGN §4-2) | DESIGN 4-2 | WU-2 | Done |  |  |  |  |
| EVT-201 | EVT | candidates/{video_id}.json {"video_id","current_title","topic":"life (DESIGN §4-3) | DESIGN 4-3 | WU-3 | Done | TC-300, TC-356 |  |  |  |
| EVT-202 | EVT | approvals/{video_id}-{candidate_id}.approved.json {"video_id","candidate_id","new_title","plan_hash","approver (DESIGN §4-3) | DESIGN 4-3 | WU-5 | Done | TC-530 |  |  |  |
| EVT-203 | EVT | Studio 내보내기 CSV 열 이름은 Studio 화면의 한글/영문 헤더를 config/csv_mapping.yaml로 매핑(헤더가 달 (DESIGN §4-3) | DESIGN 4-3 | WU-6 | Done | TC-600, TC-601, TC-602, TC-605, TC-619, TC-683, TC-685 |  |  |  |
| EVT-204 | EVT | config/banned_terms.yaml {"version", "types": {"fear":[...], "medical":[...], "financ (DESIGN §4-3) | DESIGN 4-3 | WU-3 | Done |  |  |  |  |
| EVT-205 | EVT | config/settings.yaml + config/settings.local.yaml 5-3 참고 (DESIGN §4-3) | DESIGN 4-3 | WU-0 | Done |  |  |  |  |
| UX-001 | UX | 처음 시작·인증: 03_manual_setup.md 완료 → auth --read → 브라우저 로그인 → SCR-001 안내 → fetch --all  (04_ux §1) | 04_ux 1 | WU-1, WU-2 | Done | TC-096 |  |  |  |
| UX-002 | UX | 후보 검증: 후보 파일 작성 → validate --file → SCR-002 리포트 → (경고/차단이면 파일 수정 후 재검증) (04_ux §1) | 04_ux 1 | WU-3 | Done | TC-041, TC-044, TC-357 |  |  |  |
| UX-003 | UX | 계획 확인(dry-run): plan --candidate N → SCR-003 diff와 계획 해시 → 마음에 들면 UX-004, 아니면 후보 수정 (04_ux §1) | 04_ux 1 | WU-4 | Done | TC-511 |  |  |  |
| UX-004 | UX | 승인: approve --candidate N --approver 이름 → SCR-004 승인 완료(만료 시각 표시) (04_ux §1) | 04_ux 1 | WU-5 | Done |  |  |  |  |
| UX-005 | UX | 실제 적용: apply --candidate N --live → SCR-005 적용 전 요약(영상 ID 직접 입력으로 확인) → 적용 → SCR-006  (04_ux §1) | 04_ux 1 | WU-5 | Done |  |  |  |  |
| UX-006 | UX | 되돌리기: rollback --change N --live → SCR-005와 같은 확인 → SCR-006 결과 (04_ux §1) | 04_ux 1 | WU-4, WU-5 | Done |  |  |  |  |
| UX-007 | UX | 성과 보기: report --video ID (또는 --import-csv) → SCR-008 (04_ux §1) | 04_ux 1 | WU-6 | Done | TC-666 |  |  |  |
| UX-008 | UX | 문제 해결: 오류 발생 → SCR-009 오류 안내 → 안내된 명령 실행 → 재시도 (04_ux §1) | 04_ux 1 | WU-0 | Done |  |  |  |  |
| UX-009 | UX | 오래된 기록 정리: purge --before 날짜 → SCR-010 삭제 대상·자동 DB 사본·보존 목록 확인 → 확인 입력 → 완료 (04_ux §1) | 04_ux 1 | WU-0 | Done |  |  |  |  |
| SCR-001 | SCR | 메인 도움말 (--help) — 무엇을 할 수 있는지 한눈에 (04_ux §2) | 04_ux 2 | WU-0 | Done | TC-055, TC-056, TC-526, TC-962, TC-982 |  |  |  |
| SCR-002 | SCR | 검증 리포트 — 후보별 통과/경고/차단과 이유 (04_ux §2) | 04_ux 2 | WU-3 | Done | TC-040, TC-041, TC-043, TC-044, TC-065, TC-344, TC-350, TC-354, TC-357 |  |  |  |
| SCR-003 | SCR | 계획(dry-run) diff — 무엇이 어떻게 바뀌는지 (04_ux §2) | 04_ux 2 | WU-4 | Done | TC-438, TC-445, TC-500, TC-505, TC-506, TC-511 |  |  |  |
| SCR-004 | SCR | 승인 완료 — 승인 파일 생성 확인 (04_ux §2) | 04_ux 2 | WU-5 | Done | TC-553, TC-559, TC-970, TC-974 |  |  |  |
| SCR-005 | SCR | 적용 전 요약·확인 — 마지막 사람 확인 (04_ux §2) | 04_ux 2 | WU-5 | Done | TC-520, TC-684, TC-951, TC-954, TC-984 |  |  |  |
| SCR-006 | SCR | 적용·롤백 결과 — 결과와 사후 검증 (04_ux §2) | 04_ux 2 | WU-5 | Done | TC-684, TC-954, TC-957, TC-984 |  |  |  |
| SCR-007 | SCR | 조회 요약 (fetch) — 가져온 내용 확인 (04_ux §2) | 04_ux 2 | WU-2 | Done | TC-275, TC-277, TC-280, TC-282, TC-289, TC-290 |  |  |  |
| SCR-008 | SCR | 성과 리포트 — 변경 전후 비교 (04_ux §2) | 04_ux 2 | WU-6 | Done | TC-630, TC-634, TC-635, TC-636, TC-649, TC-662, TC-663, TC-664, TC-666, TC-670 |  |  |  |
| SCR-009 | SCR | 오류 안내 — 막혔을 때 다음 행동 (04_ux §2) | 04_ux 2 | WU-0 | Done | TC-955 |  |  |  |
| SCR-010 | SCR | 데이터 정리 확인 (purge) — 삭제 전 확인 (04_ux §2) | 04_ux 2 | WU-0 | Done | TC-066, TC-067, TC-070 |  |  |  |
| ADR-001 | ADR | Python 3.12 + venv, 3.10+ 호환 (근거: 사용자 기본값, 개발자 초보) (DESIGN §11) | DESIGN 11 | - | 결정됨 |  |  |  | DEC-13 |
| ADR-002 | ADR | SQLite(sqlite3 표준 모듈), 마이그레이션 번호제 (근거: 사용자 기본값, 단일 사용자) (DESIGN §11) | DESIGN 11 | - | 결정됨 |  |  |  | DEC-14 |
| ADR-003 | ADR | argparse + commands/ 자동 탐색 (근거: 의존성 최소, 단위별 파일 분리로 병렬 충돌 방지) (DESIGN §11) | DESIGN 11 | - | 결정됨 |  |  |  | DEC-15 |
| ADR-004 | ADR | OAuth 설치형 앱, 읽기·쓰기 토큰 분리, 토큰은 사용자 프로필 폴더 (근거: 최소 권한, 저장소 유출 방지, Windows 파일 권한 한계) (DESIGN §11) | DESIGN 11 | - | 결정됨 |  |  |  | DEC-16 |
| ADR-005 | ADR | 쓰기 안전 설계 14단계(3중 조건+계획 해시 승인+허용 목록+재조회+사후 검증) (근거: v1 안전장치와 위협 모델) (DESIGN §11) | DESIGN 11 | - | 결정됨 |  |  |  | DEC-17 |
| ADR-006 | ADR | 쿼터 날짜는 America/Los_Angeles, zoneinfo+tzdata (근거: 1단계 c·3-5, Windows tzdata 필요) (DESIGN §11) | DESIGN 11 | - | 결정됨 |  |  |  | DEC-18 |
| ADR-007 | ADR | 후보는 파일 입력, 프로그램은 LLM 비호출 (근거: 사용자 기본값(DEC-003), 규칙 J 비해당) (DESIGN §11) | DESIGN 11 | - | 결정됨 |  |  |  | DEC-19 |
| ADR-008 | ADR | 쿼터 선예약 후 호출, 실패해도 차감 유지 (근거: 보수적(상한 초과 방지)) (DESIGN §11) | DESIGN 11 | - | 결정됨 |  |  |  | DEC-20 |
| ADR-009 | ADR | 공식 Google 클라이언트 라이브러리 사용 (근거: 인증·재시도 오류 감소) (DESIGN §11) | DESIGN 11 | - | 결정됨 |  |  |  | DEC-21 |
| ADR-010 | ADR | 설정 계층(settings.yaml+settings.local.yaml), enable_live·허용 목록은 local에서만 유효 (근거: 실수로 enable_live=true를 커밋·공유하는 사고 방지) (DESIGN §11) | DESIGN 11 | - | 결정됨 |  |  |  | DEC-22 |
| RISK-001 | RISK | 오해 소지 있는 제목: 영상에 없는 내용을 약속하는 제목으로 스팸·기만 정책 위반 (02_risk_assessment) | 완화로 연결된 SEC/POL/FR의 설계 § | - | Not Started |  |  |  | 완화: FR-002·FR-004 영상 내용 일치 점검과 근거 문장 기록, 일치율이 낮으면 경고·차단, POL-001 |
| RISK-002 | RISK | 시니어 대상 공포 조장: "이거 안 하면 큰일" 류로 불안을 자극 (02_risk_assessment) | 완화로 연결된 SEC/POL/FR의 설계 § | - | Not Started |  |  |  | 완화: FR-002 공포 조장 유형 차단, FR-003 사전 수정 가능 |
| RISK-003 | RISK | 건강·금융 단정 표현: 효능 단정, 수익·원금 보장 (02_risk_assessment) | 완화로 연결된 SEC/POL/FR의 설계 § | - | Not Started |  |  |  | 완화: POL-001 엄격 모드(경고도 차단, 키워드 감지 시 `topic` 무관 승격), FR-002, POL-002 면책 문구. **법률 자문 필요** |
| RISK-004 | RISK | 사칭 오인: 사실이 아닌 "정부 발표", "속보", "긴급 공지" 제목 (02_risk_assessment) | 완화로 연결된 SEC/POL/FR의 설계 § | - | Not Started |  |  |  | 완화: FR-002 사칭 오인 유형 차단 |
| RISK-005 | RISK | 과도한 제목 변경 빈도: 잦은 변경으로 신뢰·알고리즘·정책 문제 (02_risk_assessment) | 완화로 연결된 SEC/POL/FR의 설계 § | - | Not Started |  |  |  | 완화: FR-014, SEC-004 (72시간 간격, 횟수 상한, 최소 노출 수) |
| RISK-006 | RISK | 쿼터 소진: 하루 한도를 넘겨 다른 작업(Studio 연동 도구)까지 막힘 (02_risk_assessment) | 완화로 연결된 SEC/POL/FR의 설계 § | - | Not Started |  |  |  | 완화: FR-015, SEC-002 (60% 상한, 초과 시 즉시 중단), SEC-003 (재시도 2회 제한으로 재시도 폭주 방지), SEC-007 (다중 프로젝트 쿼터 확장 금지), N |
| RISK-007 | RISK | 토큰·credentials 유출: 로그·저장소에 노출되어 채널 탈취 가능 (02_risk_assessment) | 완화로 연결된 SEC/POL/FR의 설계 § | - | Not Started |  |  |  | 완화: SEC-008 (`.env` 분리, 로그 마스킹, 파일 권한, `.gitignore`), K-6 로그 스캔 테스트 |
| RISK-008 | RISK | 설명·태그 등 덮어쓰기: videos.update에서 지정하지 않은 속성이 삭제됨 (02_risk_assessment) | 완화로 연결된 SEC/POL/FR의 설계 § | - | Not Started |  |  |  | 완화: FR-009, SEC-005 (snippet 전체 백업 + 제목만 변경), SEC-010 (적용 후 재조회 검증), SEC-006 롤백 |
| RISK-009 | RISK | Studio 수동 수정과의 경합: 사람이 바꾼 제목을 프로그램이 덮어씀 (02_risk_assessment) | 완화로 연결된 SEC/POL/FR의 설계 § | - | Not Started |  |  |  | 완화: SEC-009 (호출 직전 재조회, 불일치 시 중단) |
| RISK-010 | RISK | 후보 JSON 변조·경로 조작: 악의적/오류 입력으로 잘못된 영상·경로 접근 (02_risk_assessment) | 완화로 연결된 SEC/POL/FR의 설계 § | - | Not Started |  |  |  | 완화: SEC-011 (스키마·`video_id` 형식·크기 검증) |
| RISK-011 | RISK | 공식 A/B 진행 중 API로 제목을 바꾸는 경우의 영향이 불명(테스트 교란 가능) (02_risk_assessment) | 완화로 연결된 SEC/POL/FR의 설계 § | - | Not Started |  |  |  | 완화: FR-008 dry-run에 "A/B 테스트 중인 영상이 아닌지 확인" 문구, FR-019 순차 교체 기본 비활성, POL-003 (공식 A/B 불가 영상군 제외), 운영 체크리스 |
| RISK-012 | RISK | OAuth 토큰 만료로 중단(Testing 모드는 약 7일) (02_risk_assessment) | 완화로 연결된 SEC/POL/FR의 설계 § | - | Not Started |  |  |  | 완화: FR-016 만료 감지·재인증 안내(NFR-007), 03 가이드의 운영 방식 선택지 |
| RISK-013 | RISK | 공식 원문 미확인으로 인한 오류(정책·쿼터·범위 값이 다름) 및 AI 관련 고지 의무 미확인 (02_risk_assessment) | 완화로 연결된 SEC/POL/FR의 설계 § | - | Not Started |  |  |  | 완화: 모든 값은 설정값, 도메인 허용 후 원문 재확인, POL-004 출처 기록, 규칙 F 재산정 |
| RISK-014 | RISK | 순차 비교의 신뢰도 한계를 무시한 잘못된 결론 (02_risk_assessment) | 완화로 연결된 SEC/POL/FR의 설계 § | - | Not Started |  |  |  | 완화: FR-018 한계 문구 상시 표기, 결론 단정 금지 |
| RISK-015 | RISK | 계정 경고·제재(누적 정책 위반) (02_risk_assessment) | 완화로 연결된 SEC/POL/FR의 설계 § | - | Not Started |  |  |  | 완화: 위 RISK-001~004 완화의 종합, 실제 수정은 SEC-001 (사람 승인 없는 쓰기 금지)과 3중 조건 + 사람 승인(FR-012), 비공개 테스트 영상부터(SEC-012) |
| RISK-016 | RISK | 신규 의존성의 환각·악성 패키지(AI가 코드를 작성하는 구조) (02_risk_assessment) | 완화로 연결된 SEC/POL/FR의 설계 § | - | Not Started |  |  |  | 완화: SEC-013 (PyPI 실존·라이선스 확인, 버전 고정), 9단계 점검 |
| RISK-017 | RISK | Windows 환경 문제(실행 정책, 경로·인코딩, 가상환경) (02_risk_assessment) | 완화로 연결된 SEC/POL/FR의 설계 § | - | Not Started |  |  |  | 완화: NFR-001·NFR-002, 03 가이드와 RUNBOOK의 문제 해결 절차 |
| OOS-001 | Out-of-Scope | 제목 후보 자동 생성(LLM API 호출) — v1 YT-00 질문 3 기본값. 포함하면 규칙 J와 Tier 재평가 필요 (02 §4-2) |  | - | Out-of-Scope(사유 명시) |  |  |  |  |
| OOS-002 | Out-of-Scope | 설명·태그·썸네일 수정 — 범위 최소화. 덮어쓰기 위험(RISK-008)을 줄이기 위해 제목만 변경 (02 §4-2) |  | - | Out-of-Scope(사유 명시) |  |  |  |  |
| OOS-003 | Out-of-Scope | 비공식 크롤링, 브라우저 자동화로 Studio 조작 — v1 §5-7 금지 (02 §4-2) |  | - | Out-of-Scope(사유 명시) |  |  |  |  |
| OOS-004 | Out-of-Scope | 다채널·다계정·SaaS화 — 본인 소유 단일 채널 도구 (02 §4-2) |  | - | Out-of-Scope(사유 명시) |  |  |  |  |
| OOS-005 | Out-of-Scope | 작업 스케줄러 자동 실행 — v1 YT-00 질문 5 기본값(수동 CLI). 12단계 이후 선택 사항 (02 §4-2) |  | - | Out-of-Scope(사유 명시) |  |  |  |  |
| OOS-006 | Out-of-Scope | 공식 A/B 테스트의 시작·결과 조회 — API 지원 근거 없음(1단계 b) (02 §4-2) |  | - | Out-of-Scope(사유 명시) |  |  |  |  |

## 웹 전환 요구사항 (2026-10-10, DEC-032~038; 원본 `웹프로그램으로수정요청.md` 6~9장, 설계 `docs/yt/WEB_DESIGN.md`)

| ID | 유형 | 요구사항/기능 (출처 문서 §) | 설계 매핑 (WEB_DESIGN §) | 작업 단위 | 구현 상태 | 단위테스트 (TC-ID) | 통합테스트 (IT-ID) | 전체테스트 (UAT-ID) | 비고 |
|----|------|------|------|------|------|------|------|------|------|
| W-001 | W | compose 한 번(start.ps1)으로 시작·종료·재시작·상태·로그, 127.0.0.1 접속 (요청 §6-1) | 1, 7 | W-INF | In Progress | | | | M1=데모 모드 |
| W-002 | W | 구글 로그인(읽기→쓰기 분리)을 웹에서 시작·확인·해제 — M2 (요청 §6-1) | 3 /google | W-BE-B(M2) | In Progress | | | | M1=데모 모드 |
| W-003 | W | 영상 목록(200개) 표, 검색·정렬·필터 (요청 §6-1) | 3 /videos | W-BE-B, W-FE | In Progress | | | | M1=데모 모드 |
| W-004 | W | 영상별 AI 제목 후보 생성(어댑터, 모의 AI는 M1) (요청 §6-1) | 3 /suggestions, 4 | W-BE-B, W-FE | In Progress | | | | M1=데모 모드 |
| W-005 | W | 후보 자동 검증(통과/경고/차단), 차단은 반영 불가 (요청 §6-1) | 3·4 | W-BE-B, W-FE | In Progress | | | | M1=데모 모드 |
| W-006 | W | 변경 전/후 제목·유지 항목 비교(diff) (요청 §6-1) | 6 | W-FE | In Progress | | | | M1=데모 모드 |
| W-007 | W | 후보 선택·수정·승인·반려, 일괄 선택 (요청 §6-1) | 3 /suggestions | W-BE-B, W-FE | In Progress | | | | M1=데모 모드 |
| W-008 | W | 승인 항목을 배치로 묶어 하루 한도 내 반영, 초과분 다음 날 예약, 놓친 예약 몰아서 실행 금지 (요청 §6-1) | 3 /batches, 4 | W-BE-B, W-FE | In Progress | | | | M1=데모 모드 |
| W-009 | W | 배치 사전 점검 요약과 확인 문구(`실행 {n}건`) (요청 §6-1) | 3 /batches | W-BE-B, W-FE | In Progress | | | | M1=데모 모드 |
| W-010 | W | 반영 진행 상황·중지, 재시작·실패에도 이중 반영 없음 (요청 §6-1) | 4, 2 | W-BE-A, W-BE-B, W-FE | In Progress | | | | M1=데모 모드 |
| W-011 | W | 개별/배치 롤백(영상 ID 직접 입력) (요청 §6-1) | 3 /changes | W-BE-B, W-FE | In Progress | | | | M1=데모 모드 |
| W-012 | W | 변경 이력·감사 로그 조회 (요청 §6-1) | 3 /changes /audit | W-BE-A, W-BE-B, W-FE | In Progress | | | | M1=데모 모드 |
| W-013 | W | 전후 성과 비교 리포트(화면·CSV, 데이터 부족 명시) (요청 §6-1) | 3 /reports | W-BE-B, W-FE | In Progress | | | | M1=데모 모드 |
| W-014 | W | 설정 화면(안전 설정만, 라이브 허용은 API로 변경 불가) (요청 §6-1) | 3 /settings | W-BE-A, W-FE | In Progress | | | | M1=데모 모드 |
| W-015 | W | 기존 CLI 유지(회귀·비상용, DEC-034 Q-4) (요청 §6-1) | 1 | (기존 src/ytitle) | In Progress | | | | M1=데모 모드 |
| W-016 | W | 백업·복원(pg_dump), 복원 후 건수 검증 (요청 §6-1) | 7 | W-INF | In Progress | | | | M1=데모 모드 |
| W-017 | W | /healthz·/readyz와 화면 상태 요약 (요청 §6-1) | 3 | W-BE-A, W-FE | In Progress | | | | M1=데모 모드 |
| D-01 | D | compose 4서비스+migrate, healthy 순서, 프로필 (요청 §7) | 1, 5 | W-INF | In Progress | | | | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분 |
| D-02 | D | 호스트 게시 127.0.0.1 한정, 실측 테스트 (요청 §7) | 1, 5 | W-INF | In Progress | | | | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분 |
| D-03 | D | 비루트·read_only·cap_drop·no-new-privileges (요청 §7) | 1, 5 | W-INF | In Progress | | | | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분 |
| D-04 | D | 이미지 다이제스트 고정·멀티 스테이지 (요청 §7) | 1, 5 | W-INF | In Progress | | | | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분 |
| D-05 | D | .dockerignore, 이미지에 비밀 없음 검사 (요청 §7) | 1, 5 | W-INF | In Progress | | | | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분 |
| D-06 | D | 비밀은 secrets 파일로 주입 (요청 §7) | 1, 5 | W-INF | In Progress | | | | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분 |
| D-07 | D | 데이터는 명명 볼륨, down -v 금지 (요청 §7) | 1, 5 | W-INF | In Progress | | | | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분 |
| D-07a | D | PostgreSQL 하드닝·역할 분리·pg_hba (요청 §7) | 1, 5 | W-INF, W-BE-A | In Progress | | | | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분 |
| D-07b | D | Alembic만으로 스키마 변경 (요청 §7) | 1, 5 | W-BE-A | In Progress | | | | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분 |
| D-08 | D | 헬스체크·재시작·우아한 종료·로그 제한 (요청 §7) | 1, 5 | W-INF, W-BE-A | In Progress | | | | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분 |
| D-09 | D | 시간대·로캘(UTC 저장, KST 표시) (요청 §7) | 1, 5 | W-INF, W-BE-A | In Progress | | | | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분 |
| D-10 | D | 외부 통신은 구글·AI만, internal 네트워크 (요청 §7) | 1, 5 | W-INF | In Progress | | | | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분 |
| D-11 | D | 이미지 취약점·SBOM, 의존성 잠금 (요청 §7) | 1, 5 | W-INF (9단계) | In Progress | | | | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분 |
| D-12 | D | Windows 스크립트(start/stop/backup/restore) (요청 §7) | 1, 5 | W-INF | In Progress | | | | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분 |
| D-13 | D | 테스트용 임시 컨테이너 harness-tmp 접두사·정리 (요청 §7) | 1, 5 | W-INF | In Progress | | | | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분 |
| D-14 | D | 자원 상한(메모리/CPU) (요청 §7) | 1, 5 | W-INF | In Progress | | | | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분 |
| F-01 | F | React+TS strict+Vite, ESLint·Prettier·타입 검사 (요청 §8) | 6 | W-FE | In Progress | | | | |
| F-02 | F | API 타입은 계약에서 생성/동기화, TanStack Query (요청 §8) | 6 | W-FE | In Progress | | | | |
| F-03 | F | 200행 목록 서버측 필터·정렬·페이지네이션, 선택 상태 유지 (요청 §8) | 6 | W-FE | In Progress | | | | |
| F-04 | F | 외부 CDN·원격 폰트·분석 금지 (요청 §8) | 6 | W-FE | In Progress | | | | |
| F-05 | F | dangerouslySetInnerHTML 금지, 외부 문자열은 텍스트 (요청 §8) | 6 | W-FE | In Progress | | | | |
| F-06 | F | CSRF·Idempotency-Key 자동 부착, 중복 클릭 방지 (요청 §8) | 6 | W-FE | In Progress | | | | |
| F-07 | F | 로딩·빈·오류·한도 초과·세션 만료·연결 끊김·새로고침 복구 화면 (요청 §8) | 6 | W-FE | In Progress | | | | |
| F-08 | F | 한국어 UI, 문구 한곳 관리, dry-run은 '미리보기' (요청 §8) | 6 | W-FE | In Progress | | | | |
| F-09 | F | 접근성 WCAG 2.2 AA 목표(키보드·포커스·대비) (요청 §8) | 6 | W-FE | In Progress | | | | |
| F-10 | F | PC 우선, 최신 Chrome/Edge (요청 §8) | 6 | W-FE | In Progress | | | | |
| F-11 | F | 디자인 시스템(토큰·컴포넌트) 먼저 (요청 §8) | 6 | W-FE | In Progress | | | | |
| S-W01 | SEC | 127.0.0.1에만 게시 (요청 §9) | 5 | W-INF | 구현 중 | | | | |
| S-W02 | SEC | 세션 인증·CSRF·Host/Origin(+Sec-Fetch-Site) 검증 (요청 §9) | 5 | W-BE-A | 구현 완료(6단계 대기) | | | | |
| S-W03 | SEC | 상태 변경은 GET 금지, POST/PUT/PATCH/DELETE+CSRF+확인 (요청 §9) | 5 | W-BE-A, W-BE-B | 구현 중 | | | | |
| S-W04 | SEC | 쿠키 속성·보안 헤더 (요청 §9) | 5 | W-BE-A, W-INF | 구현 중 | | | | |
| S-W05 | SEC | XSS 방어(외부 문자열 텍스트 처리) (요청 §9) | 5 | W-FE | 구현 중 | | | | |
| S-W06 | SEC | 프롬프트 인젝션 방어(입력 데이터 구분·응답 검증·권한 없음) (요청 §9) | 5 | W-BE-B | 구현 중 | | | | |
| S-W07 | SEC | 외부 AI 전송 최소화·비용 상한(실서비스 M3) (요청 §9) | 5 | W-BE-B | M1 모의만 | | | | |
| S-W08 | SEC | OAuth state·PKCE·비밀 보관(M2) (요청 §9) | 5 | W-BE-B | M2 대기 | | | | |
| S-W09 | SEC | 로그 JSON·비밀 마스킹, 오류에 스택트레이스 없음 (요청 §9) | 5 | W-BE-A | 구현 완료(6단계 대기) | | | | |
| S-W10 | SEC | CSV 업로드 검증(M2) (요청 §9) | 5 | W-BE-B | M2 대기 | | | | |
| S-W11 | SEC | 신규 의존성 실존·라이선스·취약점 확인 (요청 §9) | 5 | W-BE-A, W-FE, W-INF | 구현 중(9단계 확인) | | | | |
| S-W12 | SEC | 동시성·멱등성·이중 반영 방지(트랜잭션·행 잠금·고유 제약) (요청 §9) | 5 | W-BE-A, W-BE-B | 구현 완료(A)/중(B) | | | | |
| S-W13 | SEC | 요청 크기·속도 제한·SQL 바인딩 (요청 §9) | 5 | W-BE-A | 구현 완료(6단계 대기) | | | | |
| S-W13a | SEC | DB 보안(역할 최소 권한, 포트 미게시, 비밀번호 secrets) (요청 §9) | 5 | W-INF, W-BE-A | 구현 중 | | | | |
| S-W14 | SEC | 컨테이너 격리(비루트·읽기 전용 등) (요청 §9) | 5 | W-INF | 구현 중 | | | | |
| S-W15 | SEC | 위협 모델 STRIDE 웹·컨테이너 갱신 (요청 §9) | 5 | (M4 설계 문서) | 대기 | | | | |
| S-W16 | SEC | 감사 로그 추가 전용·해시 체인 (요청 §9) | 5 | W-BE-A | 구현 완료(6단계 대기) | | | | |

## 변경 이력
| 일시 | 버전 | 변경 내용 | 사유 |
|---|---|---|---|
| 2026-10-10 | v0 | 2단계 초기 생성 | 규칙 H |
| 2026-10-10 | v1 | 3·4단계: 설계 매핑, EVT·UX·SCR·ADR·신규 NFR/SEC 등록 | 규칙 H |
| 2026-10-10 | v2 | 웹 전환 요구사항(W/D/F/S-W) 등록 | 규칙 H, DEC-038 |
