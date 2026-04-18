"""메타데이터 엔드포인트 (언어/보이스 디자인 옵션)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import verify_api_key
from ..config import Settings, get_settings
from ..db import get_session
from ..engine.registry import engines_response
from ..provider_settings import effective_settings
from ..schemas import EnginesResponse, LanguageEntry, VoiceAttributeOptions

router = APIRouter(dependencies=[Depends(verify_api_key)])


# 상위 30개 프리셋 (§6.1). 전체 646개는 엔진 docs/languages.md 파싱 Phase 2.
_TOP_LANGUAGES: list[LanguageEntry] = [
    LanguageEntry(code="ko", name="한국어", english_name="Korean"),
    LanguageEntry(code="en", name="영어", english_name="English"),
    LanguageEntry(code="zh", name="중국어 (보통화)", english_name="Chinese (Mandarin)"),
    LanguageEntry(code="ja", name="일본어", english_name="Japanese"),
    LanguageEntry(code="es", name="스페인어", english_name="Spanish"),
    LanguageEntry(code="fr", name="프랑스어", english_name="French"),
    LanguageEntry(code="de", name="독일어", english_name="German"),
    LanguageEntry(code="it", name="이탈리아어", english_name="Italian"),
    LanguageEntry(code="pt", name="포르투갈어", english_name="Portuguese"),
    LanguageEntry(code="ru", name="러시아어", english_name="Russian"),
    LanguageEntry(code="ar", name="아랍어", english_name="Arabic"),
    LanguageEntry(code="hi", name="힌디어", english_name="Hindi"),
    LanguageEntry(code="id", name="인도네시아어", english_name="Indonesian"),
    LanguageEntry(code="vi", name="베트남어", english_name="Vietnamese"),
    LanguageEntry(code="th", name="태국어", english_name="Thai"),
    LanguageEntry(code="tr", name="터키어", english_name="Turkish"),
    LanguageEntry(code="pl", name="폴란드어", english_name="Polish"),
    LanguageEntry(code="nl", name="네덜란드어", english_name="Dutch"),
    LanguageEntry(code="sv", name="스웨덴어", english_name="Swedish"),
    LanguageEntry(code="uk", name="우크라이나어", english_name="Ukrainian"),
    LanguageEntry(code="ro", name="루마니아어", english_name="Romanian"),
    LanguageEntry(code="cs", name="체코어", english_name="Czech"),
    LanguageEntry(code="fi", name="핀란드어", english_name="Finnish"),
    LanguageEntry(code="he", name="히브리어", english_name="Hebrew"),
    LanguageEntry(code="el", name="그리스어", english_name="Greek"),
    LanguageEntry(code="ms", name="말레이어", english_name="Malay"),
    LanguageEntry(code="fa", name="페르시아어", english_name="Persian"),
    LanguageEntry(code="bn", name="벵골어", english_name="Bengali"),
    LanguageEntry(code="ta", name="타밀어", english_name="Tamil"),
    LanguageEntry(code="ur", name="우르두어", english_name="Urdu"),
]


_NONVERBAL_TAGS: list[str] = [
    "[laughter]", "[chuckle]", "[giggle]",
    "[sigh]",
    "[breath]", "[inhale]", "[exhale]",
    "[cough]", "[clear-throat]",
    "[surprise-oh]", "[surprise-wow]",
    "[question]",
    "[dissatisfaction]",
]


@router.get("/languages", response_model=list[LanguageEntry])
def list_languages() -> list[LanguageEntry]:
    return _TOP_LANGUAGES


@router.get("/voice-attributes", response_model=VoiceAttributeOptions)
def voice_attributes() -> VoiceAttributeOptions:
    return VoiceAttributeOptions(
        gender=["male", "female"],
        age=["child", "teenager", "young adult", "middle-aged", "elderly"],
        pitch=["very low", "low", "moderate", "high", "very high"],
        style=["whisper"],
        english_accent=[
            "american", "british", "australian", "canadian",
            "indian", "chinese", "korean", "japanese",
            "portuguese", "russian",
        ],
        chinese_dialect=[
            "河南话", "陕西话", "四川话", "贵州话",
            "云南话", "桂林话", "济南话", "石家庄话",
            "甘肃话", "宁夏话", "青岛话", "东北话",
        ],
    )


@router.get("/nonverbal-tags", response_model=list[str])
def list_nonverbal_tags() -> list[str]:
    return _NONVERBAL_TAGS


@router.get("/engines", response_model=EnginesResponse)
def list_tts_engines(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> EnginesResponse:
    return engines_response(effective_settings(settings, session))
