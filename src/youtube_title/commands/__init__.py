"""서브커맨드 패키지. 이 폴더의 모듈은 cli.py가 자동으로 찾아 등록한다(ADR-003).

각 모듈은 `register(subparsers, parent)`를 제공하고, 그 안에서 `set_defaults(func=run)`을 지정한다.
"""
