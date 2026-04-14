import os
import uuid
import threading
import traceback
from typing import Dict
from .schemas import JobStatus, AnalyzeRequest
from .graph.workflow import build_graph
from .excel_parser.parser import parse_all_files

JOBS: Dict[str, JobStatus] = {}
RESULTS: Dict[str, dict] = {}
_graph = build_graph()

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")


def _run(job_id: str, req: AnalyzeRequest):
    js = JOBS[job_id]
    js.status = "running"

    def progress(node: str, pct: int):
        js.current_node = node
        js.progress = pct

    try:
        # ── Parse Excel files ──
        progress("parse_excel", 2)
        file_paths = [os.path.join(UPLOAD_DIR, fn) for fn in req.excel_filenames]
        parsed = parse_all_files(file_paths)
        excel_data = parsed["excel_data"]
        reviews_by_asin = parsed["reviews_by_asin"]
        data_stats = parsed["stats"]

        # Synthesize reviews from competitor analysis review-related fields
        _neg_review_fields = [
            "差评总结", "差评痛点", "主要差评", "负面评价", "差评分析",
            "差评关键词", "差评关键词Top3", "买家反馈",
        ]
        _pos_review_fields = [
            "好评总结", "好评关键词", "好评关键词Top3", "主要好评",
            "评论总结", "评论摘要", "用户评价", "评价摘要", "客户反馈",
        ]
        for asin, metrics in parsed.get("competitor_analysis", {}).items():
            for field in _neg_review_fields:
                text = metrics.get(field)
                if text and str(text).strip() and len(str(text).strip()) > 10:
                    reviews_by_asin.setdefault(asin, []).append({
                        "body": str(text).strip(),
                        "rating": 2,
                        "title": field,
                        "verified_purchase": False,
                    })
            for field in _pos_review_fields:
                text = metrics.get(field)
                if text and str(text).strip() and len(str(text).strip()) > 10:
                    reviews_by_asin.setdefault(asin, []).append({
                        "body": str(text).strip(),
                        "rating": 4,
                        "title": field,
                        "verified_purchase": False,
                    })

        if not excel_data:
            raise ValueError("上传的 Excel 文件中未识别到任何产品数据，请检查文件格式")

        # ── Build initial state ──
        state = {
            "category": req.category,
            "asins": req.asins,
            "keywords": req.keywords,
            "target_margin": req.target_margin,
            "fee_rate": req.fee_rate,
            "excel_data": excel_data,
            "reviews_by_asin": reviews_by_asin,
            "market_analysis": parsed.get("market_analysis", []),
            "competitor_analysis": parsed.get("competitor_analysis", {}),
            "profit_calc": parsed.get("profit_calc", []),
            "keyword_analysis": parsed.get("keyword_analysis", []),
            "category_trends": parsed.get("category_trends", []),
            "source_conclusions": parsed.get("source_conclusions", []),
            "data_stats": data_stats,
            "warnings": [],
            "on_progress": progress,
        }
        result = _graph.invoke(state)
        RESULTS[job_id] = {
            "market": result.get("market"),
            "competition": result.get("competition"),
            "pricing": result.get("pricing"),
            "bad_reviews": result.get("bad_reviews"),
            "directions": result.get("directions"),
            "conclusion": result.get("conclusion"),
            "insights": result.get("insights", {}),
            "keyword_analysis": result.get("keyword_analysis", []),
            "category_trends": result.get("category_trends", []),
            "source_conclusions": result.get("source_conclusions", []),
            "warnings": result.get("warnings", []),
            "data_stats": result.get("data_stats"),
        }
        js.report_filename = result.get("report_path")
        js.status = "done"
        js.progress = 100
    except Exception as e:
        traceback.print_exc()
        js.status = "error"
        js.error = str(e)


def submit(req: AnalyzeRequest) -> str:
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = JobStatus(job_id=job_id, status="pending", progress=0)
    threading.Thread(target=_run, args=(job_id, req), daemon=True).start()
    return job_id


def get(job_id: str) -> JobStatus | None:
    return JOBS.get(job_id)
