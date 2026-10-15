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
| NFR-011 | NFR | 관측성: 실행 로그는 사람이 읽는 한국어 한 줄 + run_id, data/logs/youtube-title.log(회전 5MB×10). 토큰·키 마스킹(SEC-008) (DESIGN §5-1) | 5-1, 7 | WU-0 | Done | TC-012, TC-014 |  |  |  |
| POL-001 | POL | 건강·금융 주제는 엄격 모드(경고도 차단). topic 미지정 시, 또는 제목·요약에 건강·금융 키워드가 감지되면 topic 값과 무관하게 엄격 모드 (02 §7-1) | 4-3 EVT-201 topic, 3-2 | WU-3 | Done | TC-329, TC-330, TC-331, TC-354, TC-434, TC-502, TC-961, TC-973, TC-980 |  |  | 규칙 I 보수 적용(DEC-012) |
| POL-002 | POL | 검증 리포트·dry-run 출력·성과 리포트에 "이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다" 문구를 표기 (02 §7-1) | `04_ux_design.md` 면책 문구 규칙 | WU-3, WU-4, WU-6 | Partial | TC-049, TC-055, TC-275, TC-344, TC-500, TC-649, TC-662, TC-663 |  |  | 규칙 I 보수 적용(DEC-012). **CLI는 Done, 웹 화면·API·CSV에는 면책 문구가 없음 → DEF-9-007(Critical) Open**, 수정 후 재검증(TC-S9-079 계열) |
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
| W-001 | W | compose 한 번(start.ps1)으로 시작·종료·재시작·상태·로그, 127.0.0.1 접속 (요청 §6-1) | 1, 7 | W-INF | Done | TC-VI-001, 027, 031, 033, 102, 130, 131, 132, 133, 137 [I§4-3]; TC-WI-001~034 [I-note§4] |  |  | M1=데모 모드; I=COND.PASS[Open DEF-VI-001·002·003, C-02] (W-001과 결과서상 직접 연결된 열린 결함 없음). Windows Docker Desktop·PowerShell 5.1 미수행(사용자 PC, README 8절) |
| W-002 | W | 구글 로그인(읽기→쓰기 분리)을 웹에서 시작·확인·해제 — M2 (요청 §6-1) | 3 /google; WEB_DESIGN §12 | W-BE-B(M2), W-FE(M2·M3) | Implemented(M2·M3, 가짜 구글 시험만; 실제 구글 접속 미수행) | TC-M2-001~017, 020~031; TC-M3-010~013; TC-WF-200~203, 210~212 (자세한 연결은 아래 "M2·M3 요구사항 v5" 표) |  |  | 2026-10-11 갱신(이전: Not Started). 독립 검증: 프런트 CONDITIONAL(`units/web-WU-M23-FE-test.md`, DEF-VMF-001 High Open), 백엔드 독립 검증 시험 파일(`verify_m23`)은 있으나 결과서 없음(확인 필요). M1 시험 TC-WB-134, TC-VB-222 는 데모 상태 읽기 한정 |
| W-003 | W | 영상 목록(200개) 표, 검색·정렬·필터 (요청 §6-1) | 3 /videos | W-BE-B, W-FE | Done | TC-WB-113~116, 125 [B-note§7]; TC-VB-006, 321, 322 [B§4]; TC-VF-084~091, 151~157 [F부록B(F-03)]; TC-WF-027~030 [F-note§7] |  |  | M1=데모 모드; B=PASS, F=COND.PASS[Open DEF-VF-B01·B02, C-01] |
| W-004 | W | 영상별 AI 제목 후보 생성(어댑터, 모의 AI는 M1) (요청 §6-1) | 3 /suggestions, 4 | W-BE-B, W-FE | Done | TC-WB-008~013, 018~023, 126, 128 [B-note§7]; TC-VB-010~017, 020~026, 030~032 [B§4]; TC-VF-084~095, 151~172, 184~188, 300~313 [F§4-1 AC-02(핵심 흐름 전체)] |  |  | M1=데모 모드; 모의 AI(M1) 한정, 실 AI 어댑터 M3 대기. B=PASS, F=COND.PASS[Open DEF-VF-B01·B02, C-01] |
| W-005 | W | 후보 자동 검증(통과/경고/차단), 차단은 반영 불가 (요청 §6-1) | 3·4 | W-BE-B, W-FE | Done | TC-WB-013, 024~026, 039 [B-note§7]; TC-VB-010~017, 020~026, 311, 312, 341 [B§4-1 AC2]; TC-VF-060~066, 190~193, 221, 307~308 [F§4-1 AC-08]; TC-WF-036~038 [F-note§7] |  |  | M1=데모 모드; B=PASS, F=COND.PASS[Open DEF-VF-B01·B02, C-01]. DEF-VF-001(엄격 모드 경고=차단 표시) Fixed |
| W-006 | W | 변경 전/후 제목·유지 항목 비교(diff) (요청 §6-1) | 6 | W-FE | Done | TC-WB-093, 118 [B-note§7]; TC-VB-220 [B§4]; TC-VF-107~116 [F§4 diff 시험] |  |  | M1=데모 모드; B=PASS, F=COND.PASS[Open DEF-VF-B01·B02, C-01] |
| W-007 | W | 후보 선택·수정·승인·반려, 일괄 선택 (요청 §6-1) | 3 /suggestions | W-BE-B, W-FE | Done | TC-WB-027~038, 127 [B-note§7]; TC-VB-040~045, 050~065, 314 [B§4]; TC-VF-060~066, 084~091, 190~193 [F§4-1 AC-08·선택 유지]; TC-WF-036~038 [F-note§7] |  |  | M1=데모 모드; B=PASS, F=COND.PASS[Open DEF-VF-B01·B02, C-01] |
| W-008 | W | 승인 항목을 배치로 묶어 하루 한도 내 반영, 초과분 다음 날 예약, 놓친 예약 몰아서 실행 금지 (요청 §6-1) | 3 /batches, 4 | W-BE-B, W-FE | Done | TC-WB-050, 051, 081~083 [B-note§7]; TC-VB-080~089, 097, 098, 251, 251B, 252, 303, 304, 316 [B§4]; TC-VF-309~312 [F§4-1 AC-02·AC-07·AC-09(배치 실행 흐름)] |  |  | M1=데모 모드; B=PASS, F=COND.PASS[Open DEF-VF-B01·B02, C-01]. 하루 상한·예약 표시 전용 FE TC 는 근거 미확인. DEF-VB-01(상한 초과분 영구 skipped→다음 날 이월 deferred) Fixed. API.md 보완 요청 3건(B§8)의 반영 여부는 근거 미확인 |
| W-009 | W | 배치 사전 점검 요약과 확인 문구(`실행 {n}건`) (요청 §6-1) | 3 /batches | W-BE-B, W-FE | Done | TC-WB-049, 052~061, 129, 130, 145~147 [B-note§7]; TC-VB-070~076, 120~124, 315, 319, 327 [B§4]; TC-VF-042~051, 231, 309~311 [F§4-1 AC-07] |  |  | M1=데모 모드; B=PASS, F=COND.PASS[Open DEF-VF-B01·B02, C-01] |
| W-010 | W | 반영 진행 상황·중지, 재시작·실패에도 이중 반영 없음 (요청 §6-1) | 4, 2 | W-BE-A, W-BE-B, W-FE | Done | TC-WA-098~114 [A-note§4]; TC-VA-100~113, 124, 137, 142, 167, 172, 189 [A§4-1 AC-7]; TC-WB-062~080, 085, 086, 137~141, 148~156 [B-note§7]; TC-VB-130~143, 150~156, 250, 253, 300~302, 328 [B§4-1 AC5]; TC-VF-123, 163, 171, 172, 207, 208, 217~219, 228~230, 312 [F§4-1 AC-09] |  |  | M1=데모 모드; A=PASS, B=PASS, F=COND.PASS[Open DEF-VF-B01·B02, C-01]. DEF-VA-010(응답 전 commit, A§6) Fixed — F 결과서는 같은 결함을 DEF-VF-B01 Open 으로 기재(C-01) |
| W-011 | W | 개별/배치 롤백(영상 ID 직접 입력) (요청 §6-1) | 3 /changes | W-BE-B, W-FE | Done | TC-WB-094~103, 132 [B-note§7]; TC-VB-160~178, 257, 287 [B§4-1 AC6]; TC-VF-052~059, 313 [F§4] |  |  | M1=데모 모드; B=PASS, F=COND.PASS[Open DEF-VF-B01·B02, C-01] |
| W-012 | W | 변경 이력·감사 로그 조회 (요청 §6-1) | 3 /changes /audit | W-BE-A, W-BE-B, W-FE | Done | TC-WA-073~085 [A-note§4]; TC-VA-080~087, 121, 122 [A§4-1 AC-5]; TC-WB-093, 136 [B-note§7]; TC-VB-180, 181, 210~214, 259 [B§4]; TC-VF-313 [F§4(이력 계약)] |  |  | M1=데모 모드; A=PASS, B=PASS, F=COND.PASS[Open DEF-VF-B01·B02, C-01]. 감사 로그 탭 화면의 별도 TC 는 근거 미확인. 감사 꼬리 절단은 알려진 제한(TC-VA-084 특성화) |
| W-013 | W | 전후 성과 비교 리포트(화면·CSV, 데이터 부족 명시) (요청 §6-1) | 3 /reports | W-BE-B, W-FE | Done | TC-WB-104~112, 133 [B-note§7]; TC-VB-190~200, 320 [B§4-1 AC7]; TC-VF-187, 319 [F§4]; TC-WF-064, 065 [F-note§7] |  |  | M1=데모 모드; B=PASS, F=COND.PASS[Open DEF-VF-B01·B02, C-01] |
| W-014 | W | 설정 화면(안전 설정만, 라이브 허용은 API로 변경 불가) (요청 §6-1) | 3 /settings | W-BE-A, W-FE | Done | TC-WA-059~072 [A-note§4]; TC-VA-056~065, 147~150, 176 [A§4-1 AC-3]; TC-VF-069~072, 238, 315, 316 [F§4-1 AC-05]; TC-WF-067, 069, 070, 094, 095 [F-note§7] |  |  | M1=데모 모드; A=PASS, F=COND.PASS[Open DEF-VF-B01·B02, C-01]. 라이브 허용 변경 불가: TC-VA-056~058, TC-VF-316 |
| W-015 | W | 기존 CLI 유지(회귀·비상용, DEC-034 Q-4) (요청 §6-1) | 1 | (기존 src/youtube_title) | Partial(근거 미확인) | 근거 미확인(웹 4개 결과서에 CLI 회귀 시험 기록 없음) |  |  | M1=데모 모드; 기존 CLI 는 FR-001~020 행에서 Done. 웹 결과서(A·B·F·I)에 W-015 회귀 근거 없음(C-07) |
| W-016 | W | 백업·복원(pg_dump), 복원 후 건수 검증 (요청 §6-1) | 7 | W-INF | Done | TC-VI-025, 026, 029, 030, 064, 131 [I§4-1 AC5] |  |  | M1=데모 모드; I=COND.PASS[Open DEF-VI-001·002·003, C-02]. 관찰 O-VI-03(-SkipSafetyBackup 실패 시 안내 문구 오류), O-VI-04 |
| W-017 | W | /healthz·/readyz와 화면 상태 요약 (요청 §6-1) | 3 | W-BE-A, W-FE | Done | TC-WA-133~146 [A-note§4(헬스)]; TC-VA-007, 008, 094 [A§4]; TC-VI-046, 109, 120 [I§4-3]; TC-VB-222 [B§4]; TC-VF-029~031, 040, 136, 137, 189, 194~197, 214 [F§4-1 AC-04] |  |  | M1=데모 모드; A=PASS, F=COND.PASS[Open DEF-VF-B01·B02, C-01], I=COND.PASS[Open DEF-VI-001·002·003, C-02] |
| D-01 | D | compose 4서비스+migrate, healthy 순서, 프로필 (요청 §7) | 1, 5 | W-INF | Partial(dev/test 프로필 미구현) | TC-VI-009, 100, 109, 123, 133 [I§4-2]; TC-WI-016 [I-note§4] |  |  | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분; I=COND.PASS[Open DEF-VI-001·002·003, C-02]. 프로필 미구현은 노트 선언(M1 범위 밖, 테스트는 YTWEB_PROJECT 분리로 대체), 수용 여부는 I 질문 6 대기 |
| D-02 | D | 호스트 게시 127.0.0.1 한정, 실측 테스트 (요청 §7) | 1, 5 | W-INF | Done | TC-VI-001, 040, 102, 132B [I§4-2]; TC-WI-001, 002, 030 [I-note§4] |  |  | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분; I=COND.PASS[Open DEF-VI-001·002·003, C-02]. Linux 엔진 실측, Docker Desktop 미수행 |
| D-03 | D | 비루트·read_only·cap_drop·no-new-privileges (요청 §7) | 1, 5 | W-INF | Done | TC-VI-002, 003, 014, 100, 101 [I§4-2]; TC-WI-003~008, 032 [I-note§4] |  |  | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분; I=COND.PASS[Open DEF-VI-001·002·003, C-02]. Linux 엔진 실측 |
| D-04 | D | 이미지 다이제스트 고정·멀티 스테이지 (요청 §7) | 1, 5 | W-INF | Done | TC-VI-013, 015, 016, 108, 136 [I§4-2]; TC-WI-022 [I-note§4] |  |  | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분; I=COND.PASS[Open DEF-VI-001·002·003, C-02]. TC-VI-136 은 공식 연속 실행에서 skipped, 단독 재실행 Pass(I§4) |
| D-05 | D | .dockerignore, 이미지에 비밀 없음 검사 (요청 §7) | 1, 5 | W-INF | Done | TC-VI-018, 036, 037, 107, 108 [I§4-2]; TC-WI-021, 029 [I-note§4] |  |  | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분; I=COND.PASS[Open DEF-VI-001·002·003, C-02]. 이미지 레이어 비밀 스캐너(Trivy 등) 미수행(9단계). I 노트는 '부분', I 결과서는 '충족(스캐너 미수행)' (C-04) |
| D-06 | D | 비밀은 secrets 파일로 주입 (요청 §7) | 1, 5 | W-INF | Done | TC-VI-008, 036, 107, 137 [I§4-2]; TC-WI-009, 018, 026 [I-note§4] |  |  | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분; I=COND.PASS[Open DEF-VI-001·002·003, C-02] |
| D-07 | D | 데이터는 명명 볼륨, down -v 금지 (요청 §7) | 1, 5 | W-INF | Done | TC-VI-004, 027, 028, 132, 133, 134 [I§4-2]; TC-WI-004, 012, 020 [I-note§4] |  |  | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분; I=COND.PASS[Open DEF-VI-001·002·003, C-02] |
| D-07a | D | PostgreSQL 하드닝·역할 분리·pg_hba (요청 §7) | 1, 5 | W-INF, W-BE-A | Done | TC-VI-011, 021~023, 060~064, 110, 111, 113 [I§4-2]; TC-VA-114~120, 173, 193~196 [A§4]; TC-WI-017, 018, 025, 026 [I-note§4] |  |  | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분; A=PASS, I=COND.PASS[Open DEF-VI-001·002·003, C-02]. I 결과서는 DEF-VI-002(alembic_version 앱 DML)를 Open·TC-VI-112 xfail 로 기재, A 결과서는 같은 결함을 DEF-VA-012(0002 마이그레이션)로 Fixed 기재(C-02). audit-guard.sql 추가 제안 반영 근거 미확인 |
| D-07b | D | Alembic만으로 스키마 변경 (요청 §7) | 1, 5 | W-BE-A | Done | TC-VA-114~120, 173, 193~196 [A§4]; TC-VI-009, 123 [I§4-2]; TC-WI-016, 019 [I-note§4] |  |  | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분; A=PASS, I=COND.PASS[Open DEF-VI-001·002·003, C-02]. 실행 전 자동 백업은 미구현(노트 선언). I 노트는 '부분', I 결과서는 '충족(미구현 선언)' (C-04) |
| D-08 | D | 헬스체크·재시작·우아한 종료·로그 제한 (요청 §7) | 1, 5 | W-INF, W-BE-A | Done | TC-VI-009, 010, 109, 121, 122 [I§4-2]; TC-VA-007, 113, 137 [A§4(헬스·SIGTERM 우아한 종료)]; TC-WI-014, 015 [I-note§4] |  |  | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분; A=PASS, I=COND.PASS[Open DEF-VI-001·002·003, C-02]. api 종료 코드 143 관찰(O-VI-02) — I 노트의 '종료 시 exit 0' 과 불일치(C-04). 워커 헬스체크는 프로세스 생존만 |
| D-09 | D | 시간대·로캘(UTC 저장, KST 표시) (요청 §7) | 1, 5 | W-INF, W-BE-A | Done | TC-VI-010, 060, 113 [I§4-2]; TC-VA-144~146 [A§4-1 AC-14(KST/PT 날짜)]; TC-WI-017 [I-note§4] |  |  | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분; A=PASS, I=COND.PASS[Open DEF-VI-001·002·003, C-02] |
| D-10 | D | 외부 통신은 구글·AI만, internal 네트워크 (요청 §7) | 1, 5 | W-INF | Partial(DEF-VI-001 Open: web 컨테이너 외부 egress·db 도달) | TC-VI-005, 006, 103~106 [I§4-2]; TC-WI-010, 011, 031 [I-note§4] (TC-VI-106 은 xfail 로 결함 고정) |  |  | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분; I=COND.PASS[Open DEF-VI-001·002·003, C-02]. 열린 결함 DEF-VI-001(Medium, 설계 변경·사용자 결정 대기, Deferred 로 DEC 기록 없음). api/worker/db 는 충족. I 노트는 D-10 '충족' (C-04) |
| D-11 | D | 이미지 취약점·SBOM, 의존성 잠금 (요청 §7) | 1, 5 | W-INF (9단계) | Partial(취약점·SBOM 미수행, 9단계 대기) | TC-VI-017 [I§4-2(잠금 부분)] |  |  | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분; 의존성 해시 잠금만 시험됨. 취약점 스캔·SBOM 은 9단계. I=COND.PASS[Open DEF-VI-001·002·003, C-02] |
| D-12 | D | Windows 스크립트(start/stop/backup/restore) (요청 §7) | 1, 5 | W-INF | Done | TC-VI-027~034, 130~137, 130B [I§4-2]; TC-WI-027, 033 [I-note§4] |  |  | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분; I=COND.PASS[Open DEF-VI-001·002·003, C-02]. Linux pwsh 7.5.4 로만 실행, Windows·PS 5.1·ACL 경로 미수행 |
| D-13 | D | 테스트용 임시 컨테이너 harness-tmp 접두사·정리 (요청 §7) | 1, 5 | W-INF | Done | TC-VI-100, 109, 131, 133, 137 [I§3(harness-tmp-vi 접두사 실가동 시험)] |  |  | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분; I=COND.PASS[Open DEF-VI-001·002·003, C-02]. 정리 확인은 I§7 |
| D-14 | D | 자원 상한(메모리/CPU) (요청 §7) | 1, 5 | W-INF | Done | TC-VI-007, 100 [I§4-2]; TC-WI-013 [I-note§4] |  |  | 클라우드 Linux 엔진 실측 + 사용자 PC(Docker Desktop) 확인 구분; I=COND.PASS[Open DEF-VI-001·002·003, C-02] |
| F-01 | F | React+TS strict+Vite, ESLint·Prettier·타입 검사 (요청 §8) | 6 | W-FE | Done | TC-WF-081 [F-note§7] (정적 검사 tsc·ESLint·Prettier·build 는 F§4-2, TC-ID 없음) |  |  | F=COND.PASS[Open DEF-VF-B01·B02, C-01] |
| F-02 | F | API 타입은 계약에서 생성/동기화, TanStack Query (요청 §8) | 6 | W-FE | Partial(OpenAPI 타입 생성 미적용: 계약 수동 전사) | TC-ID 없음(TanStack Query 는 화면 시험 전반, F-note§7) |  |  | F 부록 B 도 'F-02(타입 생성 제외)'. F=COND.PASS[Open DEF-VF-B01·B02, C-01] |
| F-03 | F | 200행 목록 서버측 필터·정렬·페이지네이션, 선택 상태 유지 (요청 §8) | 6 | W-FE | Partial(가상 스크롤 미적용, WEB_DESIGN §6 완화) | TC-VF-084~091, 151~157, 204, 211~213 [F부록B]; TC-WF-027~030 [F-note§7] |  |  | F=COND.PASS[Open DEF-VF-B01·B02, C-01] |
| F-04 | F | 외부 CDN·원격 폰트·분석 금지 (요청 §8) | 6 | W-FE | Done | TC-WF-083 [F-note§7] |  |  | F=COND.PASS[Open DEF-VF-B01·B02, C-01] |
| F-05 | F | dangerouslySetInnerHTML 금지, 외부 문자열은 텍스트 (요청 §8) | 6 | W-FE | Done | TC-VF-037, 038, 092, 097~102, 106, 114 [F§4-1 AC-12]; TC-WF-018, 081 [F-note§7] |  |  | F=COND.PASS[Open DEF-VF-B01·B02, C-01] |
| F-06 | F | CSRF·Idempotency-Key 자동 부착, 중복 클릭 방지 (요청 §8) | 6 | W-FE | Done | TC-VF-001~022, 035, 036, 227, 309, 317 [F§4-1 AC-11]; TC-WF-001, 005~008, 012, 044, 046, 050, 051, 055, 060 [F-note§7] |  |  | F=COND.PASS[Open DEF-VF-B01·B02, C-01] |
| F-07 | F | 로딩·빈·오류·한도 초과·세션 만료·연결 끊김·새로고침 복구 화면 (요청 §8) | 6 | W-FE | Done | TC-VF-104, 105, 148~150, 158, 180, 181, 185, 186, 188, 189, 194~197, 206 [F§4-1 AC-15·AC-04]; TC-WF-031~033, 041~043, 048, 052~054, 059, 063, 065, 072, 073, 076~079 [F-note§7] |  |  | F=COND.PASS[Open DEF-VF-B01·B02, C-01] |
| F-08 | F | 한국어 UI, 문구 한곳 관리, dry-run은 '미리보기' (요청 §8) | 6 | W-FE | Partial(AC-14 일부 관찰: OBS-2 용어 혼용, OBS-4 문구 7곳 ko.ts 밖) | TC-VF-164~166, 225, 239 [F§4-1 AC-14]; TC-WF-049, 084 [F-note§7] |  |  | F=COND.PASS[Open DEF-VF-B01·B02, C-01]. 사용자 질문 Q1 대기. 결함이 아니라 관찰로 분류됨 |
| F-09 | F | 접근성 WCAG 2.2 AA 목표(키보드·포커스·대비) (요청 §8) | 6 | W-FE | Done | TC-VF-117~119, 124~145 [F§4-1 AC-13]; TC-WF-019~021, 024, 086~093 [F-note§7] |  |  | F=COND.PASS[Open DEF-VF-B01·B02, C-01]. 실브라우저 axe 34화면 위반 0. 스크린리더·Edge·실기기 미수행 |
| F-10 | F | PC 우선, 최신 Chrome/Edge (요청 §8) | 6 | W-FE | Done | TC-ID 없음(F§4-3 실브라우저 1024·1280px 가로 넘침 없음) |  |  | F=COND.PASS[Open DEF-VF-B01·B02, C-01]. Chromium 1194 만 시험, Edge 미수행. 375px 가로 넘침은 설계 비대상으로 관찰 OBS-3 |
| F-11 | F | 디자인 시스템(토큰·컴포넌트) 먼저 (요청 §8) | 6 | W-FE | Done | TC-ID 없음(F-note§6 토큰·F§4-3 axe 라이트/다크) |  |  | F=COND.PASS[Open DEF-VF-B01·B02, C-01] |
| S-W01 | SEC | 127.0.0.1에만 게시 (요청 §9) | 5 | W-INF | Done | TC-VI-001, 012, 019, 040, 049, 102 [I§4-3]; TC-WI-001, 002, 030 [I-note§4] |  |  | I=COND.PASS[Open DEF-VI-001·002·003, C-02]. Linux 엔진 실측, Docker Desktop 미수행 |
| S-W02 | SEC | 세션 인증·CSRF·Host/Origin(+Sec-Fetch-Site) 검증 (요청 §9) | 5 | W-BE-A | Done | TC-VA-001~015, 033, 034, 039~042, 074 [A§4-1 AC-1]; TC-WA-001~004, 024~058 [A-note§4]; TC-VF-001~022, 317 [F§4-1 AC-11] |  |  | A=PASS, F=COND.PASS[Open DEF-VF-B01·B02, C-01]. 실제 Chrome/Edge 에서 쿠키·Sec-Fetch-Site 동작(Q-WA-1) 미수행 |
| S-W03 | SEC | 상태 변경은 GET 금지, POST/PUT/PATCH/DELETE+CSRF+확인 (요청 §9) | 5 | W-BE-A, W-BE-B | Done | TC-VA-010, 012, 014, 036, 039~042, 056~061, 074 [A§4-1 AC-1·AC-3]; TC-WA-024~072 [A-note§4]; TC-WB-123 [B-note§7]; TC-VB-231, 233, 279 [B§12]; TC-VF-002, 003, 317 [F§4] |  |  | A=PASS, B=PASS, F=COND.PASS[Open DEF-VF-B01·B02, C-01] |
| S-W04 | SEC | 쿠키 속성·보안 헤더 (요청 §9) | 5 | W-BE-A, W-INF | Done | TC-VA-025, 027, 029, 030 [A§4]; TC-WA-012, 013 [A-note§4]; TC-VI-019, 020, 041~047, 050, 051 [I§4-3]; TC-WF-081 [F-note§7] |  |  | A=PASS, I=COND.PASS[Open DEF-VI-001·002·003, C-02]. 열린 결함 DEF-VI-003(Low, nginx 오류 로그에 쿼리 문자열; TC-VI-055 xfail 이 S-W04 로 표기), DEF-VI-004 Fixed. 브라우저 CSP 동작 미수행 |
| S-W05 | SEC | XSS 방어(외부 문자열 텍스트 처리) (요청 §9) | 5 | W-FE | Done | TC-VF-037, 038, 092, 097~102, 106, 114 [F§4-1 AC-12]; TC-WF-018, 081 [F-note§7] |  |  | F=COND.PASS[Open DEF-VF-B01·B02, C-01] |
| S-W06 | SEC | 프롬프트 인젝션 방어(입력 데이터 구분·응답 검증·권한 없음) (요청 §9) | 5 | W-BE-B | Done | TC-WB-008~011, 023, 024, 070 [B-note§7]; TC-VB-010~017, 020~026, 306, 340, 341 [B§4] |  |  | B=PASS. 모의 AI(M1) 한정 — 실 AI 응답 검증은 M3 에서 재확인 필요 |
| S-W07 | SEC | 외부 AI 전송 최소화·비용 상한(실서비스 M3) (요청 §9) | 5 | W-BE-B | Partial(M1 모의 AI 한정, 실서비스 M3 대기) | TC-WB-011, 018 [B-note§7]; TC-VB-030~032 [B§12] |  |  | B=PASS. 비용 상한 시험 근거 미확인 |
| S-W08 | SEC | OAuth state·PKCE·비밀 보관(M2) (요청 §9) | 5 | W-BE-B | Implemented(코드·가짜 구글 시험만; 독립 검증·9단계 재검증 미수행) | TC-M2-001~006, 009, 014, 026~029, 031; TC-M3-013 (`web/backend/tests/test_google_oauth.py`, `tests/domain/test_google_router.py`, `tests/domain/test_live_gateway.py`) |  |  | 2026-10-11 갱신(이전: 시험 없음). A 결과서의 S-W08 표기(세션·PIN TC)는 여전히 정의 불일치(C-03)이며 이 행의 TC 로 세지 않음. 위협 TW-37~38·42(`threat_model.md` W9). 실제 구글 환경 미검증 |
| S-W09 | SEC | 로그 JSON·비밀 마스킹, 오류에 스택트레이스 없음 (요청 §9) | 5 | W-BE-A | Done | TC-VA-007, 026, 041, 064, 088~099 [A§4-1 AC-4·AC-13]; TC-WA-017~023, 126~132 [A-note§4] |  |  | A=PASS |
| S-W10 | SEC | CSV 업로드 검증(M2) (요청 §9) | 5 | W-BE-B | Not Started(M2 대기) | 시험 없음 |  |  | CSV 업로드(M2). 내보내기(W-013)와 별개 |
| S-W11 | SEC | 신규 의존성 실존·라이선스·취약점 확인 (요청 §9) | 5 | W-BE-A, W-FE, W-INF | Partial(9단계 확인 대기, A 라이선스 개별 확인 미수행) | TC-VI-017 [I§4-2(잠금)] (F: npm audit 취약점 0, F§4-2·F-note§11 — TC-ID 없음) |  |  | A 노트 §5: PyPI 실존·버전 확인, 라이선스 미확인. I: 취약점·SBOM 9단계. I=COND.PASS[Open DEF-VI-001·002·003, C-02] |
| S-W12 | SEC | 동시성·멱등성·이중 반영 방지(트랜잭션·행 잠금·고유 제약) (요청 §9) | 5 | W-BE-A, W-BE-B | Done | TC-VA-066~079, 100~113, 124, 137 [A§4-1 AC-6·AC-7]; TC-WA-086~114 [A-note§4]; TC-WB-064, 129~132, 137~143 [B-note§7]; TC-VB-130~143, 250, 253, 255, 256, 258, 260, 261 [B§4] |  |  | A=PASS, B=PASS. DEF-VA-009(PIN 실패 카운터 동시성, High) Fixed. 권고 R-3(complete() 펜싱 없음) |
| S-W13 | SEC | 요청 크기·속도 제한·SQL 바인딩 (요청 §9) | 5 | W-BE-A | Done | TC-VA-016~024, 151~158, 168, 169 [A§4-1 AC-12]; TC-WA-005~011 [A-note§4]; TC-WB-114, 122, 125, 127 [B-note§7]; TC-VB-237~239 [B§12] |  |  | A=PASS, B=PASS |
| S-W13a | SEC | DB 보안(역할 최소 권한, 포트 미게시, 비밀번호 secrets) (요청 §9) | 5 | W-INF, W-BE-A | Done | TC-VI-011, 021~023, 060~064, 110, 111, 113 [I§4-2]; TC-VA-118~120, 193~196 [A§4-1 AC-8]; TC-WA-147~157 [A-note§4] |  |  | A=PASS, I=COND.PASS[Open DEF-VI-001·002·003, C-02]. I 결과서 부록 D 에 S-W13a 표기 없음(C-05); DEF-VI-002 Open ↔ DEF-VA-012 Fixed(C-02) |
| S-W14 | SEC | 컨테이너 격리(비루트·읽기 전용 등) (요청 §9) | 5 | W-INF | Done | TC-VI-002, 003, 100, 101 [I§4-2(D-03 시험 재사용)]; TC-WI-003~008, 032 [I-note§4] |  |  | I=COND.PASS[Open DEF-VI-001·002·003, C-02]. I 결과서에 S-W14 직접 표기 없음, D-03 시험으로 간접 연결(C-05) |
| S-W15 | SEC | 위협 모델 STRIDE 웹·컨테이너 갱신 (요청 §9) | 5 | (M4 설계 문서) | Not Started(M4 설계 문서 대기) | 시험 대상 아님(설계 문서 갱신) |  |  | 근거: 작업 단위가 (M4 설계 문서) |
| S-W16 | SEC | 감사 로그 추가 전용·해시 체인 (요청 §9) | 5 | W-BE-A | Done | TC-VA-080~087, 118, 121, 122, 143, 174, 175, 180 [A§4-1 AC-5]; TC-WA-073~085, 147~157 [A-note§4]; TC-VB-210~214, 259 [B§4] |  |  | A=PASS, B=PASS. 꼬리 절단·전체 재작성은 체인으로 탐지 불가(알려진 제한, TC-VA-084), 방어선은 DB 권한 회수(TC-VA-118) |
| POL-005 | POL | 데모 모드 상시 표시: "데모 모드 — 유튜브에 아무것도 전송되지 않습니다" (02_planning §W7-1) | WEB_DESIGN 6(화면); DESIGN §W9-5 표에는 매핑 없음(갭) | W-FE | Done | TC-S9-079 [S9§4: test_demo_badge_is_always_rendered_in_layout, test_bundle_contains_demo_badge_and_ai_label] |  |  | S9=FAIL 판정 단위지만 이 행은 Pass(구현분 4건 통과). 구현 위치 `Layout.tsx` demoBadge·`ko.ts`, 번들 3회 확인(S9 부록 J). 브라우저 실표시는 7단계 대기 |
| POL-006 | POL | AI 제안 표시: "AI가 생성한 제안입니다. 사람이 검토·승인한 제목만 반영됩니다."를 후보 목록·승인 화면·이력에 상시 노출 (02_planning §W7-1; 규칙 J) | WEB_DESIGN 6; threat_model Part W §W4 투명성 행(DESIGN.md 에는 해당 행 없음) | W-FE (W-FIX-4) | Not Started(고지 문장 없음; "AI 제안" 배지만 부분 존재) | TC-S9-079 [S9§4: test_ai_generated_notice_sentence_exists_and_is_on_suggestion_card, test_bundle_contains_ai_generated_notice — xfail(결함 고정)]; 배지 회귀: test_ai_label_and_strict_mode_hint_exist_on_suggestion_card |  |  | **DEF-9-007·008(Open, S9§6): 면책·AI 고지·표시광고/한계·A/B 확인 문구 미노출** — DEF-9-008(High; S9 Q-S9-10·13 은 Critical 상향 여부를 사용자 질의 중). 수정 후 xfail 표식 제거로 재검증 |
| POL-007 | POL | 외부 전송 고지: 제목+설명 요약이 외부 AI(서비스명·서버 위치)로 전송됨, 자막·성과 제외, 설명의 이름·연락처 삭제 권고 (02_planning §W7-1) | DESIGN §W9-3 외부 전송 데이터, §W9-4 제3자 제공 | W-BE-B, W-FE (M3a) | Not Started(M3 대기; 전송 자체가 없음, 마스킹은 구현) | 시험 없음(M3). 마스킹 부분은 SEC-026 행 참조 |  |  | M3 대기(Q-1 AI 서비스 미정). 고지 UI 미구현은 S9 부록 J 에서 "M3 예정" |
| POL-008 | POL | AI 한계 고지: 사실·법령 적합성 비보장, 건강·금융은 표시광고 규정 확인, 법률 자문 아님(POL-002와 병합 가능) (02_planning §W7-1) | WEB_DESIGN 6; threat_model Part W §W4 투명성·LLM09 | W-FE (W-FIX-4) | Not Started(미구현) | TC-S9-079 [S9§4: test_ai_limit_and_advertising_rule_notice_exists_and_is_on_suggestion_card, test_bundle_contains_advertising_rule_notice — xfail(결함 고정)] |  |  | **DEF-9-007·008(Open, S9§6): 면책·AI 고지·표시광고/한계·A/B 확인 문구 미노출** — DEF-9-008(High). 번들 검색 "표시광고" 0건 |
| POL-009 | POL | 반영 한도: 하루 반영 건수 기본 10(최대 20)·배치당 50, 영상별 72시간 간격·영상당 3회 (02_planning §W7-1) | WEB_DESIGN 4-3(한도); DESIGN §W5(쓰기 안전 게이트) | W-BE-A, W-BE-B | Done | TC-VB-080~091, 097, 098 [B§4]; TC-VA-062, 147~150 [A§4-1]; TC-S9-027·028 [S9§4: 50건 초과 배치 불가, daily_cap_bounds] |  |  | M1=데모 모드. 구현 `routers/settings.py`(1~20)·`domain/common.py` MAX_BATCH_ITEMS=50·`config/settings.yaml`. Q-3 해석 대기(02_planning §W11). W-008 행과 같은 시험을 공유 |
| POL-010 | POL | 라이브 반영 허용·허용 영상 목록은 설정 API로 변경 불가(별도 확인 절차는 M3에서 설계) (02_planning §W7-1) | DESIGN §W9-1 S-W03; WEB_DESIGN 4 | W-BE-A | Done | TC-VA-056~059 [A§4-1 AC-3]; TC-VF-316 [F§4-1 AC-05]; TC-S9-028 [S9§4: settings_cannot_enable_live…, live_mode_cannot…] |  |  | ALLOWED_KEYS 4개. 라이브 허용 확인 절차는 M3(W-M3b)에서 설계 필요 — 현재 해당 절차 없음이 설계 |
| POL-011 | POL | 승인 정책: plan_hash·HMAC·1회용·TTL 24시간. 만료 판정 시각=배치 실행 확정 시각(DEC-042 D3 수용) — **M3에서 재정의 필요** (02_planning §W7-1) | WEB_DESIGN 4(2); DESIGN §W9-1 | W-BE-B | Done | TC-VB-050, 052, 053, 055~060, 062~064 [B§4-1]; TC-S9-027 [S9§4: 승인 변조·HMAC·1회용·만료 경계 ±1초] |  |  | M1 범위 Done. M3 재정의 필요(W-M3b). TC-S9-027 은 DB 직접 변조 시험까지 Pass |
| POL-012 | POL | 데이터 보관·파기: 롤백용 원본 snippet·성과 스냅샷·구글 유래 데이터의 보관 상한과 구글 연결 해제 시 삭제 범위·기한(가정 7일) (02_planning §W7-1) | DESIGN §W9-4 보관·파기(보관 기간 미정 Q-W06) | W-M2 (연결 해제 화면) | Not Started(미구현, 정책 미정) | 시험 없음 |  |  | DEF-9-013(S9§6, Open): `purge_expired` 는 세션만. 정책 확정(Q-W2) 필요. M2(실데이터) 전 결정 필요(RISK-025) |
| POL-013 | POL | Studio A/B 테스트 중인 영상은 사용자가 제외, 실행 확인 문구에 "A/B 테스트 중이 아님" 확인 포함(FR-C06) (02_planning §W7-1) | WEB_DESIGN 3 /batches; DESIGN §W9-5 표에는 매핑 없음(갭) | W-FE, W-BE-B (W-FIX-4) | Not Started(확인 문구 미구현; 서버 사전 점검 경고 1줄만 존재) | TC-S9-079 [S9§4: test_batch_execute_confirmation_mentions_ab_test — xfail(결함 고정)]; 경고 1줄: TC-VB-110 [B§4], test_ab_warning_exists_only_as_preflight_warning_line [S9§4] |  |  | **DEF-9-007·008(Open, S9§6): 면책·AI 고지·표시광고/한계·A/B 확인 문구 미노출** — DEF-9-008(High). 서버 사전 점검 경고(`domain/batches.py:184`)는 구현·시험됨이나 요구(확인 문구에 포함)는 미충족. WEB_LEGAL_NOTICE §A/B 도 "미구현"으로 명시 |
| POL-014 | POL | 제외 영상(Shorts·비공개·아동용·예약)은 제안 생성·승인·배치·반영 4단계에서 모두 차단하고 사유 표시(DEC-042 D4) (02_planning §W7-1) | WEB_DESIGN 4; DESIGN §W9-5 (제외 영상은 같은 표에서 "POL-003"으로 표기 — ID 불일치, 아래 비고) | W-BE-B | Done | TC-VB-004, 005, 016, 113, 241 [B§4] |  |  | 구현 `domain/exclusions.py`. S9: 코드 정독으로 확인(동작은 6단계 시험 근거). ID 불일치: DESIGN §W9-5 는 같은 기능을 POL-003, 02_planning §W7-1 은 POL-014 로 표기(사용자 확인 질문) |
| POL-015 | POL | 구글 클라우드 프로젝트 1개만 사용(테스트용 추가 프로젝트·쿼터 우회 금지). OAuth 게시 상태 선택은 사용자 결정 (02_planning §W7-1) | 03_manual_setup(매뉴얼); WEB_LEGAL_NOTICE §쿼터 | W-M2 | Not Started(M2 대기; 문서 정책만, 코드 없음) | 시험 대상 아님(문서 정책) |  |  | WEB_LEGAL_NOTICE 에 정책 문구 있음. M2 구글 클라우드 프로젝트 생성 시 적용 |
| POL-016 | POL | 백업 정책: 백업 파일 암호화 여부·보관 위치·보관 기간, 서명 키 별도 보관 (02_planning §W7-1) | DESIGN §W7-4 백업·재해복구 | W-INF, W-BE-A (W-FIX-5) | Not Started(정책 미정) | 시험 없음 (백업·복원 동작 자체는 W-016 행) |  |  | DEF-9-013(S9§6, Open): 백업 무암호화(README 경고만). 사용자 결정 Q-W4 대기. 위협 TW-12·TW-19 |
| SEC-021 | SEC | 영상 제목·설명은 비신뢰 입력: 정제(제어·방향·보이지 않는 문자 제거), 길이 상한, 지시/데이터 구획은 **보조일 뿐 보안 경계가 아님**을 설계서에 명시 (02_planning §W7-2) | DESIGN §W9-3 프롬프트 인젝션 방어 경계; threat_model LLM01 | W-BE-B (M3a: 구획) | Partial(정제·길이 상한 구현; 지시/데이터 구획은 실서비스 어댑터 없어 M3) | TC-S9-025 [S9§4]; TC-VB-020, 023 [B§4]; TC-WB-008~011 [B-note§7] |  |  | 구현 `ai/guard.py` clean_text, MAX_SUMMARY_CHARS=500. 요구 중 "지시/데이터 구획은 보안 경계가 아님을 설계서에 명시"는 DESIGN.md 에서 해당 문구를 찾지 못함(미충족 가능, 질문). S9 부록 F M3 진입 전 조건 |
| SEC-022 | SEC | AI에 도구·함수·네트워크·파일·DB·YouTube API 권한 부여 금지(텍스트 생성만) (02_planning §W7-2) | DESIGN §W9-3 도구/함수 권한 최소화; threat_model LLM06 | W-BE-B | Done(구조; 실서비스 SDK 도구 기능 비활성은 M3) | TC-S9-020 [S9§4: full_flow_makes_no_network_calls]; TC-VB-340 [B§4]; TC-S9-025 [입력=영상 ID·제목·요약뿐] |  |  | `ai/base.py` TitleSuggester.suggest() 가 세션·게이트웨이를 받지 않음. 어댑터가 api 프로세스 안이라 샌드박스 없음(DESIGN §W9-3 명시) → M3 코드 리뷰 강제 |
| SEC-023 | SEC | AI 응답은 스키마 검증 후 사용, 후보 수·길이 상한, `<` `>`·제어문자·줄바꿈·URL·연락처 후보 폐기 (02_planning §W7-2) | DESIGN §W9-3 출력 새니타이즈·렌더링; threat_model LLM05 | W-BE-B | Done | TC-S9-026 [S9§4: 악성 출력 11종]; TC-VB-021, 022, 023, 026 [B§4]; TC-WB-008~011 [B-note§7] |  |  | 구현 `sanitize_drafts`. `<` `>` 는 검증기(유튜브 제목)가 차단 판정하는 구조(02_planning 명시) |
| SEC-024 | SEC | AI 후보도 기존 검증기 통과 필수(길이 100자, 금칙어, 영상 일치, 건강·금융 엄격 모드). 차단 후보는 반영 불가 (02_planning §W7-2) | DESIGN §W9-3·§W9-5(POL-001); threat_model LLM09 | W-BE-B | Done(키워드 목록 한계 있음) | TC-S9-026, 026b [S9§4]; TC-VB-013, 014, 015, 024 [B§4]; TC-WB-013, 024~026 [B-note§7] |  |  | TC-S9-026b: 엄격 모드는 25개 키워드 의존 — 목록 밖 건강 용어+AI topic=life 이면 엄격 모드가 꺼짐(재현, OBS-3). 해결은 사용자·설계 판단 Q-W10(USER_DECISIONS Q-27) |
| SEC-025 | SEC | AI 후보는 사람 승인 없이 반영 불가(승인=plan_hash 묶음), 자동 반영 경로 금지 (02_planning §W7-2) | DESIGN §W9-3; WEB_DESIGN 4(2) | W-BE-B | Done | TC-S9-027 [S9§4]; TC-VB-025, 057 [B§4] |  |  | 구현 `check_approval`·확인 문구. 관련 POL-011 |
| SEC-026 | SEC | 외부 전송 최소화: 제목+설명 요약만, 연락처·링크·주민번호 모양 마스킹, 토큰·키·자막·성과 제외 (02_planning §W7-2) | DESIGN §W9-3 외부 전송 데이터, §W9-4 | W-BE-B | Partial(마스킹·최소 전송 구현; 전송 미리보기·영상 단위 AI 제외 옵션 미구현) | TC-S9-025 [S9§4]; TC-VB-030, 032 [B§4] |  |  | 미구현분은 FR-C04. S9 부록 F M3 전 조건. 위협 TW-22. POL-007 과 함께 처리 |
| SEC-027 | SEC | AI 호출 일/배치당 호출·토큰·비용 상한, 빈도 제한, 재시도 상한, 타임아웃 (02_planning §W7-2) | DESIGN §W9-3 레이트리밋·토큰 사용량(M3: NFR-W12 ③) | W-M3a | Not Started(M3 대기; 모의 AI라 상한 코드 없음) | 시험 없음 |  |  | M3 진입 차단 조건(S9 부록 F). 위협 LLM10·RISK-023. Q-1(AI 서비스·월 예산) 대기, USER_DECISIONS Q-24 |
| SEC-028 | SEC | AI 키는 secrets로만 주입, 로그·DB·백업·화면 노출 금지, 프롬프트 원문 비저장 (02_planning §W7-2) | DESIGN §W9-3 시스템 프롬프트·내부 로직 유출 방지; threat_model LLM07 | W-BE-B, W-INF (M3a) | Partial(prompt_hash 저장·로그 마스킹 구현; 키 주입 경로는 M3) | TC-VB-031 [B§4: ai_run 은 해시만 저장]; TC-VA-098 [A§4: JSON 로그 마스킹] |  |  | 키 주입 경로 미구현(M3). 로그 마스킹은 S-W09 행과 공유 |
| SEC-029 | SEC | AI 응답 문자열은 항상 텍스트로 렌더링 (02_planning §W7-2) | DESIGN §W9-3 출력 렌더링; F-05 | W-FE | Done | TC-S9-022 [S9§4]; TC-VF-037, 038, 092, 097~102, 106, 114 [F§4-1 AC-12]; TC-WF-018 [F-note§7] |  |  | F-05·S-W05 행과 같은 시험. 소스 grep 0·ESLint 규칙 근거(S9 부록 J) |
| SEC-030 | SEC | 인젝션 시험 세트(지시 무시·형식 탈취·비밀 요구·다른 영상 제목·과장 후크)를 9단계에서 수행, 누락은 Critical (02_planning §W7-2) | threat_model LLM01·TW-15; 9단계 인계(Part W §W7) | W-BE-B (M3a: 실서비스) | Partial(M1 모의 AI 정제 시험만; 실서비스 어댑터 시험은 M3) | TC-S9-026 [S9§4]; TC-VB-020 [B§4]; TC-WB-008~011 [B-note§7] |  |  | S9 에서 인젝션·출력 기반 XSS 직접 재현 시도는 불성립. 실서비스 LLM 인젝션 시험은 M3(S9§2 제외 범위). 누락 시 Critical 규칙은 M3 착수 시 적용 |

### 웹 전환 요구사항 시험 연결 요약 (v4, 2026-10-11)

약어(구현 상태·단위테스트·비고 컬럼): `S9`=`security-web-m1-test.md`(9단계 보안 결과서, `TC-S9-nnn`; 테스트 코드는 `web/tests_security/` 의 함수 이름으로 연결돼 있고 번호 자체는 결과서에만 있음), `A`=`units/web-WU-BE-A-test.md`, `B`=`web-WU-BE-B-test.md`, `F`=`web-WU-FE-test.md`, `I`=`web-WU-INF-test.md`, `X-note`=해당 단위 `web-WU-*-note.md`, `§n`=문서 절/부록. `TC-WA/WB/WF/WI`=구현자 시험, `TC-VA/VB/VF/VI`=6단계 독립 검증 시험. `C-nn`=`docs/harness/verify-log_web-traceability.md` 의 모순·누락 목록 번호. 단위 판정: A=PASS, B=PASS, F=CONDITIONAL PASS, I=CONDITIONAL PASS. TC-ID 는 `web/backend/tests`, `web/frontend/{src,verify}`, `web/tests_infra` 에서 실제 존재를 확인했다(v3 1410개 참조 전부 존재; v4 신규 POL/SEC 행 TC 88개 전부 존재, TC-S9 8개는 결과서 정의 및 `web/tests_security` 함수명 존재 확인, 검증 로그 v4 1차).

v4 추가분(POL/SEC 22행)은 02_planning §W7-1(POL)·§W7-2(SEC)의 정의를 그대로 옮겼으며 새 ID 를 만들지 않았다. 구현 상태는 02_planning "구현 상태(웹)" 열과 9단계 결과서(부록 J) 대조 결과다. POL-006·008·013 은 9단계 결함 DEF-9-007·008 로 Open(Not Started)이며, 관련 xfail 시험이 결함을 고정한다.

| 구분 | 요구사항 수 | TC 연결 | TC 미연결 | 비고 |
|---|---|---|---|---|
| W (기능) | 17 | 16 | 1 | W-015 |
| D (배포) | 16 | 16 | 0 | - |
| F (프런트) | 11 | 8 | 3 | F-02, F-10, F-11 |
| S-W (보안) | 17 | 14 | 3 | S-W08, S-W10, S-W15 |
| POL (정책, v4) | 12 | 8 | 4 | POL-007, 012, 015, 016. POL-006·008·013 은 xfail(결함 고정) 시험으로만 연결 |
| SEC (AI 안전, v4) | 10 | 9 | 1 | SEC-027 |
| **합계** | **83** | **71** | **12** | 연결률 85.5% (v3 88.5% 에서 신규 22행 반영으로 하락) |

구현 상태 분포: Done 58, Not Started 12, Partial 13 (Deferred·Blocked 는 0건: 결과서에 해당 DEC-ID·차단 기록 없음). v4 신규 22행은 Done 10(POL-005·009·010·011·014, SEC-022·023·024·025·029), Partial 4(SEC-021·026·028·030), Not Started 8(POL-006·007·008·012·013·015·016, SEC-027). 근거 미확인 상태 행 0건.

| 미연결 ID | 구현 상태 | 사유 |
|---|---|---|
| W-015 | Partial(근거 미확인) | 웹 4개 결과서에 CLI 회귀 시험 기록 없음(근거 미확인, C-07) |
| F-02 | Partial(OpenAPI 타입 생성 미적용: 계약 수동 전사) | OpenAPI 타입 생성 미적용(계약 수동 전사), TC-ID 없음 |
| F-10 | Done | 실브라우저 점검(F§4-3)만 있고 TC-ID 없음 |
| F-11 | Done | 토큰·axe 점검만 있고 TC-ID 없음 |
| S-W08 | SEC | OAuth state·PKCE·비밀 보관(M2) (요청 §9) | 5 | W-BE-B | Implemented(코드·가짜 구글 시험만; 독립 검증·9단계 재검증 미수행) | TC-M2-001~006, 009, 014, 026~029, 031; TC-M3-013 (`web/backend/tests/test_google_oauth.py`, `tests/domain/test_google_router.py`, `tests/domain/test_live_gateway.py`) |  |  | 2026-10-11 갱신(이전: 시험 없음). A 결과서의 S-W08 표기(세션·PIN TC)는 여전히 정의 불일치(C-03)이며 이 행의 TC 로 세지 않음. 위협 TW-37~38·42(`threat_model.md` W9). 실제 구글 환경 미검증 |
| S-W10 | Not Started(M2 대기) | M2 대기(CSV 업로드) |
| S-W15 | Not Started(M4 설계 문서 대기) | M4 설계 문서 대기(시험 대상 아님) |
| POL-007 | Not Started(M3 대기) | M3 대기(외부 AI 전송 자체가 없음) |
| POL-012 | Not Started(미구현, 정책 미정) | 시험 없음, DEF-9-013 |
| POL-015 | Not Started(M2 대기) | 문서 정책(시험 대상 아님) |
| POL-016 | Not Started(정책 미정) | 시험 없음, DEF-9-013 |
| SEC-027 | Not Started(M3 대기) | AI 호출·비용 상한 코드 없음(M3 진입 차단 조건) |

통합테스트(IT)·전체테스트(UAT) 컬럼은 이번 갱신 범위가 아니어서 비워 두었다.

### M2·M3 요구사항 (v5, 2026-10-11; 구글 읽기 연동·제목 수정, DEC-046~048, 설계 `WEB_DESIGN.md` §12)

> **ID 주의(규칙 H)**: 아래 `W-M2-xx`·`W-M3-xx`·`S-W17` 은 11단계 문서 갱신 중 이 표에 맞춰 임시로 붙인 **미승인 ID**이다. 정식 ID 부여·02단계 기획서 반영은 오케스트레이터 확인이 필요하다(확인 필요). 기존 `W-002`·`S-W08`·`POL-010`·`POL-012`·`POL-015` 행도 함께 해당된다. 시험 파일·함수는 존재를 확인했으나(2026-10-11 `grep`), 이 갱신에서 시험을 다시 실행하지는 않았다(마지막 실행 결과는 `STATE.md`의 "M3 회귀 시험": 백엔드 전체 1461 통과·96 건너뜀·실패 0, 프런트 659 통과·2 실패(별도 시험 코드 문제)).

| ID | 유형 | 요구사항/기능 | 설계 매핑 | 작업 단위 | 구현 상태 | 단위테스트 (TC-ID / 파일) | 통합테스트 (IT-ID) | 전체테스트 (UAT-ID) | 비고 |
|----|------|------|------|------|------|------|------|------|------|
| W-M2-01 | W | 구글 읽기 OAuth(데스크톱 앱 클라이언트, state 1회용 10분·PKCE S256, 토큰 0600 원자 저장) | WEB_DESIGN §12-1; DEC-048 | M2 단위 1 | Implemented(가짜 구글만) | TC-M2-001~017 (`web/backend/tests/test_google_oauth.py`) |  |  | 실제 구글 접속 미수행. 클라이언트 유형 변경(DEC-034 Q-5 → 데스크톱 앱) |
| W-M2-02 | W | 로그인 API connect·callback·status·disconnect, 구글 비밀 파일·통신 경로(compose.online.yaml, `_common.ps1`) | WEB_DESIGN §12-1·§3; API.md EVT-W31~35 | M2 단위 2 | Implemented(가짜 구글만) | TC-M2-020~031 (`web/backend/tests/domain/test_google_router.py`); 인프라 정적 시험(실패 0, STATE 기록) |  |  | 콜백은 S-W03 의 GET 예외. Windows 스크립트 실행 미수행 |
| W-M2-03 | W | 내 채널 영상 읽기(channels→uploads→videos, 최대 2,000개)·videos 저장·데모 영상 보호(`demo_data_in_use`) | WEB_DESIGN §12-2 | M2 단위 3 | Implemented(가짜 구글만) | TC-M2-040~053 (`web/backend/tests/domain/test_live_sync.py`) |  |  | 미시험: 이 프로그램이 바꾼 적 있는 영상의 보존 로직(STATE 기록) |
| W-M2-04 | F | 화면 "구글(유튜브) 연결" 카드(연결·불러오기·해제·오류 안내) | WEB_DESIGN §12-5 | M2 단위 4 | Implemented | TC-WF-200~203 (`web/frontend/src/pages/google.test.tsx`); 독립: TC-VMF-xxx (`verify_m23/google.verify.test.tsx`) |  |  | E2E 21/21(37초, STATE 기록). 독립 검증 CONDITIONAL — DEF-VMF-001(High, Open) |
| W-M3-01 | W | 쓰기 권한 별도 로그인(`youtube.force-ssl`, `google_write_token.json` 분리)·제목 수정 게이트웨이(허용 영상만, 모호 응답=반영 여부 불명) | WEB_DESIGN §12-2·§12-4 | M3 단위 1·2 | Implemented(가짜 구글만) | TC-M3-010~013 (`web/backend/tests/domain/test_live_gateway.py`); `test_live_write.py` 시험 7개(함수명 `test_scope_and_auth_url_write` 등, TC-ID 없음) |  |  | 실제 제목 변경 없음. 사용자 승인 전 실제 반영 금지(규칙 E) |
| W-M3-02 | W | 게이트웨이 선택 3조건(YTWEB_LIVE_WRITE=1 + 쓰기 토큰 + 허용 영상 1개 이상)·반영 확인 시 videos 동기화 | WEB_DESIGN §12-3 | M3 단위 2 | Partial — 켜는 방법 미정 | TC-M3-020·021·030·031 (`test_live_gateway.py`) |  |  | **환경변수를 컨테이너에 전달하는 설정이 저장소에 없음**(확인 필요, DEF-VMF-004, Q-11-10). `config.MODES` 는 아직 `("demo",)` 뿐이며(YTWEB_MODE 는 demo 고정) 실제 쓰기는 별도 환경변수 3조건으로만 선택됨 — 의도된 설계인지 확인 필요 |
| W-M3-03 | W | 실제 모드 안전장치: 확인 문구 `실제 실행 N건`, 허용 외 영상 `live_not_allowed`(초안·반영 직전·롤백), 변경 기록 mode live/demo | WEB_DESIGN §12-4 | M3 단위 4 | Implemented(가짜 구글만) | TC-M3-040~047 (`web/backend/tests/domain/test_live_guard.py`) |  |  | 프런트 확인 문구 표시 시험 없음(서버 문구 표시), "A/B 중 아님" 서버 필드는 M3 결정 대기(DEC-047 ②) |
| W-M3-04 | F | 화면 "제목 수정 권한" 구역(연결·꺼짐·실제 모드 경고) | WEB_DESIGN §12-5 | M3 단위 3 | Implemented | TC-WF-210~212 (`google.test.tsx`) |  |  | DEF-VMF-002~004(Low) Open |
| W-M3-05 | F | 모드 표시 정확성: 구글 연결·실제 모드 상태에서 상단 띠·연결 상태 칸이 사실을 표시 | WEB_DESIGN §12-6 | (후속 조치 예정) | **Not Started — 결함 DEF-VMF-001(High, Open)** | 결함 고정 시험 TC-VMF-140·141·142 (`web/frontend/verify_m23/google.verify.test.tsx`) |  |  | 실제 구글 연결 전 수정 필수. 위협 TW-40 |
| S-W17 | SEC | M2·M3 위협 대응(콜백 위조·쓰기 토큰·허용 목록 우회·확인 문구 우회·모호 응답·토큰 로그 유출) | `threat_model.md` W9(TW-37~44) | M2·M3 | Partial(문서화됨; 독립 검증·9단계 재검증 미수행) | TC-M2-003~006, 008, 011, 026~029; TC-M3-012, 013, 031, 042, 046, 047; `test_tc_vb_278`(외부 통신 허용 모듈 3개 한정) |  |  | TW-38(쓰기 토큰 암호화 없음·revoke 미구현) 사용자 수용 결정 대기 |
| POL-015 | POL | (기존 행 보강) 구글 클라우드 프로젝트 1개만 사용 | 03_manual_setup; WEB_LEGAL_NOTICE §10 | W-M2 | 문서 정책(변경 없음) | 시험 대상 아님 |  |  | 기존 POL-015 행 상태는 그대로이며 여기서는 M2 실행 시 확인 항목으로만 재언급 |
| POL-012 | POL | (기존 행 보강) 구글 유래 데이터·토큰 보관·삭제 | WEB_LEGAL_NOTICE §10 | W-M2 | Not Started(정책 미정, 변경 없음) | 시험 없음 |  |  | [연결 해제]는 토큰만 삭제, videos·이력·감사 로그는 남음(코드 확인). 정책 확정 필요 |

M2·M3 v5 요약: 신규 임시 행 12개(POL 보강 2행 포함) 중 시험 연결 10행, 시험 없음 2행(POL-012·015, 시험 대상 아님/정책 미정), 구현 상태는 Implemented 7·Partial 2·Not Started 1(W-M3-05)·정책행 2. **전체 연결률 숫자는 재계산하지 않았다**(기존 83행 표의 85.5% 는 이 갱신 전 값).

### v6 (2026-10-13): 세션 신규 기능 W-N01~11, 시험 연결 없던 요구 11개 분류, 결과서 ID 34개 정정

> **ID 주의(규칙 H)**: `W-N01`~`W-N11` 은 임시 번호이며 **선생님이 2026-10-13 추가를 승인**했다(정식 번호 부여·02단계 기획서 반영은 별도). 요구 설명은 코드·시험에서 확인한 사실만 적었다. "이번 실행"은 2026-10-13 이 갱신 작업에서 해당 시험만 돌린 결과다(첫 실행 그대로, 실패 없음).

| ID | 유형 | 요구사항/기능 | 설계 매핑 | 구현 상태 | 단위테스트 (TC-ID / 파일) | 이번 실행 | 비고 |
|----|------|------|------|------|------|------|------|
| W-N01 | W | 규칙 기반 제안기: 설명의 챕터에서 제목 후보 생성, 후보는 검증기를 통과 | WEB_DESIGN §12 | Implemented | `web/backend/tests/test_rule_suggester.py` 5건 | 5 통과 | 임시 ID(승인됨) |
| W-N02 | W | Gemini 제안기: 키 파일 `web/secrets/gemini_api_key`, 키는 헤더로만 전송, 제목+설명 요약만 전송, 오류 한국어, 이미 만든 제목 전달, 502/503 등 재시도, 출력 한도 16384 | 13c1b2a | Implemented(가짜 응답 시험. 실서버 확인은 `docs/harness/units/web-fullcheck-parts/e-gemini-traceability.md`) | `test_gemini_suggester.py` 8건, `test_gemini_retry.py` 10건, `domain/test_live_suggest.py` 5건 | 23 통과 | 외부 AI 전송 고지(POL-007)는 미구현 |
| W-N03 | W | 실제 영상 제안은 승인 가능 후보만·충분한 길이 | 631a14c, 08074b5 | Implemented | `domain/test_live_suggest.py::test_live_video_gets_only_approvable_candidates_of_sufficient_length` | 통과 | DEF-LIVE-001 |
| W-N04 | W | 반영 후 검증: 줄바꿈·끝 공백·태그 순서·언어 자동 채움 완화, 달라진 항목 표시 | e1bfa0c | Implemented | `domain/test_verify_report.py` 3건 | 3 통과 | CLI 의 SEC-010 과 별개 |
| W-N05 | W | 유튜브에서 직접 바꾼 제목도 불러오기 때 갱신(반영 진행 중 영상 제외), 직접 고친 제목 출처 구분 | 722ae2c, b5a5b9d | Implemented | `domain/test_live_sync.py::test_tc_live_sync_refreshes_a_video_changed_by_the_program_and_by_hand_but_not_one_in_flight`, TC-M3-060 (`domain/test_source_edit.py`) | 통과 | |
| W-N06 | F | AI 제안 종류 표시(모의/규칙/Gemini/직접 고침/옛 제안) | 1fcef8a | Implemented | `web/frontend/src/pages/ai.aibadge.test.tsx` 7건, `verify_ai_badge/` 2건 | 7 + 2 통과 | |
| W-N07 | F | 실행 버튼 비활성일 때 남은 조건 표시 | 1fcef8a | Implemented | `batchdetail.execgate.test.tsx` 4건 | 4 통과 | 선생님 질문("체크도 해야 하나요?") 근거 |
| W-N08 | F | 입력칸에 id 또는 name | 1fcef8a | Implemented | `formids.test.tsx` (it/test 11개 호출) | 통과 | |
| W-N09 | W | 실제 모드 꺼짐 상태에서 실제 영상은 배치 포함 불가·모의 성공 처리 금지 | 0306011 (DEF-LIVE-005) | Implemented | `domain/test_live_off_block.py` 3건 | 3 통과 | |
| W-N10 | W | 실제 수정 준비 점검(live-check) | b5a5b9d | Implemented | TC-M3-070·071 (`domain/test_live_check.py`) | 2 통과 | |
| W-N11 | F | 제안 카드 점검 점수·색 구분 | 8d672d1 | Implemented | `web/frontend/src/lib/score.test.ts` 7건 | 7 통과 | `SuggestionCard.tsx` 에서 사용 |

**시험 연결이 없던 요구 11개의 분류 (원문: `docs/yt/02_planning.md`, `DESIGN.md`)**

| ID | 분류 | 조치·근거 |
|---|---|---|
| NFR-006 | (a) 시험 추가 | `web/backend/tests/verify_trace/test_trace_unlinked.py::test_tc_trace_nfr006_validator_and_request_body_line_coverage_at_least_90` — validator.py·live_guard.py(요청 본문 구성 `build_write_body`)·updater.py 줄+분기 커버리지 각 100%(CLI 시험 6개 파일 실행). 통과 |
| SEC-013 | (a) 시험 추가(부분) | `test_tc_trace_sec013_*` — 의존성 파일 4개 `==` 고정과 웹 잠금 파일 해시 존재만 시험. "공식 레지스트리에 실존·라이선스 확인"은 사람이 하는 절차라 시험하지 않음(S-W11 라이선스 미확인과 같은 이유). 통과 |
| W-015 | (a) 시험 추가 | `test_tc_trace_w015_*` — CLI `--help` 동작, 웹이 `youtube_title` 를 임포트하고 복사본이 없음, CLI 회귀 시험 4개 파일 통과. 통과 |
| S-W10 | (b) 미구현·결정 대기 | CSV 업로드 엔드포인트 없음(M2 대기). `test_tc_trace_sw10_csv_upload_endpoint_exists` 를 xfail(strict)로 표시해 구현되면 알림 |
| POL-007 | (b) 미구현 | 외부 AI 전송 고지(서비스명·서버 위치·자막 제외·이름/연락처 삭제 권고) 문구가 프런트 소스에 없음(`자막`·`연락처` 0건). **Gemini 어댑터가 이미 외부 전송을 하므로 이전 사유 "전송 자체가 없음"은 더 이상 사실이 아님.** `test_tc_trace_pol007_*` xfail(strict) |
| SEC-027 | (a)+(b) 부분 | 일부 구현·시험: Gemini 타임아웃·재시도 횟수·출력 토큰 상한(`test_tc_trace_sec027_gemini_has_retry_cap_timeout_and_output_token_cap`, 통과). 일/배치당 호출·비용 상한·빈도 제한은 코드 없음 → `test_tc_trace_sec027_daily_or_batch_ai_call_cap_exists` xfail(strict) |
| POL-012 | (b) 미구현·결정 대기 | 보관 상한·자동 삭제 코드 없음(보안 결과서 DEF-9-013, Q-W2). 시험을 만들지 않음 |
| POL-016 | (b) 미구현·결정 대기 | 백업 암호화·보관 기간 미정(Q-W4, DEF-9-013). 시험을 만들지 않음 |
| POL-015 | (c) 시험 대상 아님 | 구글 클라우드 프로젝트 1개만 쓰는 운영 정책(코드 없음, 02_planning 원문 "문서 정책") |
| S-W15 | (c) 시험 대상 아님 | 위협 모델 문서 작성 요구. 산출물 `docs/yt/threat_model.md` Part W(TW-01~44) 존재로 확인(시험 아님) |
| NFR-001 | 사용자 PC 확인 대기 | Windows 10/11 + PowerShell 5.1 요건은 이 Linux 환경에서 시험 불가. 선생님 PC 확인 5건(README §8)에 해당. 시험 연결 없음 |

**결과서에는 있고 소스에서 못 찾았다던 ID 34개 정정**: 원인은 시험이 없어서가 아니라 **표기 차이**였다. 시험 함수명은 `TC-VI-025` → `test_tc_vi_025_...`(소문자·밑줄), 범위 `TC-WI-003~008` 는 개별 `tc_wi_003` 들. 대소문자·밑줄 변환으로 대조하면 아래 행의 TC-VI/TC-WI/TC-VB/TC-WB 계열 ID 는 **전부 실제 시험에 존재**한다(W-016, D-01·03·04·05·06·07·10·11·12·13·14, S-W06·07·11·14, POL-014, W-M3-02, S-W17: 각 행의 ID 100% 확인). 위치: `web/tests_infra/test_vi_independent.py`·`test_vinf2_*.py`·`test_fix_inf*.py`(TC-VI), `web/backend/tests/verify_wb/test_vb_*.py`(TC-VB), `web/backend/tests/core`·`domain`(TC-WB 등). 남은 ID 는 **TC-S9-nn** 이며 보안 결과서(`docs/harness/security-web-m1-test.md`)가 함수명으로 지정한다. 실제 위치는 `web/tests_security/` 이다:

| ID(S9) | 실제 시험 (파일::함수) | 연결 요구 |
|---|---|---|
| TC-S9-020 | `test_sec_02_injection_ai_integrity.py::test_full_flow_makes_no_network_calls` | SEC-022 |
| TC-S9-025 | 같은 파일 `test_build_summary_masks_pii_urls_and_caps_length`, `test_prompt_input_is_data_not_instructions_in_adapter_contract` | SEC-021·022·026 |
| TC-S9-026 / 026b | 같은 파일 `test_malicious_ai_output_is_sanitized_end_to_end`, `test_ai_cannot_downgrade_strict_mode_on_health_video`, `test_strict_keyword_list_gap_is_documented` | SEC-023·024·030 |
| TC-S9-027 | 같은 파일 `test_db_level_approval_tamper_is_detected` 외 승인 변조 시험(`test_expiry_extension_in_db_is_detected`, `test_approval_is_single_use_...`) | POL-011, SEC-025 |
| TC-S9-079 | `web/tests_security/test_sec_05_regulatory_ai_notice.py` (`test_bundle_contains_demo_badge_and_ai_label` 등, POL-006·008·013 은 xfail 고정) | POL-005·006·008·013 |

정정되지 않고 남은 불일치: 위 정정은 이름 규칙 대조 결과이며, 범위(`~`)·접미사(`130B` 등)는 끝점·변형을 개별 확인하지 않았다(한계). 결과서 파일은 수정하지 않았다.

**기존 시험의 현재 실패 1건 (이번 실행에서 확인, 결함 후보)**: `domain/test_google_router.py::test_tc_m2_030_disconnect_clears_token` 이 실패한다. 응답이 `{'connected': False, 'revoked': False}` 인데 시험은 `{'connected': False}` 를 기대한다(제품이 `revoked` 필드를 추가한 뒤 시험이 갱신되지 않은 것으로 보이나 **확인한 것은 아님**). 시험 기대값을 고치지 않고 그대로 두며, W-M2-02 는 "통과 확인"에서 제외한다.

**v6 숫자 (분모 = FR 20 + NFR 11 + POL 16 + SEC 48 + W 23 + D 16 + F 14 = 요구 행 148개 + 이번 추가 W-N 11 = 159개. EVT/UX/SCR/ADR/RISK 설계 항목 제외)**

| 지표 | 값 |
|---|---|
| 표에 시험이 기재된 행 | 154 / 159 (96.9%) — 미기재 5: NFR-001, S-W15, POL-015, POL-012, POL-016 |
| **시험이 소스에 실제 존재하는 행** | **151 / 159 (95.0%)** (직전 134/148 + W-N 11 + 이번 추가 6; 이 중 S-W10·POL-007·SEC-027 의 일부는 xfail 로 "시험은 있고 구현이 없음"). F-02·F-10 은 문서에 "TC-ID 없음"이라 존재 쪽에서 제외 |
| 이번 작업에서 실제 실행해 통과 확인 | 14 / 159 (8.8%): W-N01~11, NFR-006, SEC-013, W-015. 나머지는 8단계 기록(백엔드 1844·프런트 728 통과)에 의존하며 이번에 재실행하지 않음 |
| 이번 실행 실패 | 1 (W-M2-02 의 TC-M2-030, 위) |
| 미구현·결정 대기 | 5 (POL-012, POL-016, S-W10, POL-007, SEC-027 일부) + 표에 이미 Not Started 인 POL-006·008·013(xfail 고정) |
| 시험 대상 아님 | 2 (POL-015, S-W15) |
| 사용자 PC 확인 대기 | 1 (NFR-001) |
| 문서 증빙만(소스 시험 ID 없음) | F-02(OpenAPI 타입 생성 미적용), F-10(실브라우저 점검) |

100% 에 못 미치는 이유: 위 표 (미구현 5, 시험 대상 아님 2, 사용자 PC 1, 시험 ID 없음 F-02·F-10). F-11 은 `web/frontend/src/a11y.test.tsx`(axe 사용, 8건 통과)가 소스에 존재하나 표의 연결은 아직 고치지 않았다.

## 변경 이력
| 일시 | 버전 | 변경 내용 | 사유 |
|---|---|---|---|
| 2026-10-10 | v0 | 2단계 초기 생성 | 규칙 H |
| 2026-10-10 | v1 | 3·4단계: 설계 매핑, EVT·UX·SCR·ADR·신규 NFR/SEC 등록 | 규칙 H |
| 2026-10-10 | v2 | 웹 전환 요구사항(W/D/F/S-W) 등록 | 규칙 H, DEC-038 |
| 2026-10-11 | v3 | 웹 요구사항(W/D/F/S-W 61행) 구현 상태·단위테스트·비고를 4개 단위 결과서(A·B·F·I)와 구현 노트로 채움, 시험 연결 요약 표 추가, 모순·누락 목록은 verify-log_web-traceability.md | 규칙 H, 규칙 B |
| 2026-10-11 | v4 | 웹 정책·AI 안전 요구 POL-005~016(12행)·SEC-021~030(10행) 정식 등록(총 83행). 정의는 02_planning §W7-1·§W7-2 에서 옮김(새 ID 없음), 구현 상태·TC 는 9단계 결과서와 단위 결과서 기준, 시험 연결 요약 표 갱신. POL-006·008·013 은 DEF-9-007·008 Open 으로 연결 | DEF-9-018 조치(규칙 H·I·J 추적성) |
| 2026-10-11 | v5 | W-002·S-W08 행 갱신, "M2·M3 요구사항 v5" 표 신설(임시 ID W-M2-01~04, W-M3-01~05, S-W17 및 POL-012·015 보강 — 미승인 ID, 규칙 H 확인 필요) | M2·M3 구현 반영(DEC-048), 11단계 문서 갱신 |
| 2026-10-13 | v6 | 세션 신규 기능 W-N01~11(선생님 승인, 임시 번호) 추가, 시험 연결 없던 11개 요구 분류와 시험 3개 파일 추가(`web/backend/tests/verify_trace/`), 결과서 ID 34개 표기 차이 정정, 숫자 재계산(분모 159) | 규칙 H, 추적성 판정 TRC-1·2·3 |
