from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime

app = Flask(__name__)

DATABASE = "database.db"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            title TEXT NOT NULL,
            original_title TEXT NOT NULL DEFAULT '',

            original_priority TEXT NOT NULL DEFAULT '보통',
            original_start_date TEXT NOT NULL,
            original_end_date TEXT NOT NULL,
            original_success_criteria TEXT NOT NULL,
            original_expected_minutes INTEGER NOT NULL,

            current_priority TEXT NOT NULL DEFAULT '보통',
            current_start_date TEXT NOT NULL,
            current_end_date TEXT NOT NULL,
            current_success_criteria TEXT NOT NULL,
            current_expected_minutes INTEGER NOT NULL,

            status TEXT NOT NULL DEFAULT '진행중',

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # 수정 이력 보존을 위한 별도 테이블 생성 (T06-C08 준수)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plan_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            title TEXT NOT NULL,
            priority TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            success_criteria TEXT NOT NULL,
            expected_minutes INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT '진행중',
            modified_at TEXT NOT NULL,
            FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE
        )
    """)

    # 기존 데이터베이스 테이블 호환성 유지 (컬럼이 없을 경우 추가)
    cursor = conn.execute("PRAGMA table_info(plans)")
    columns = [row["name"] for row in cursor.fetchall()]

    if "status" not in columns:
        conn.execute("ALTER TABLE plans ADD COLUMN status TEXT NOT NULL DEFAULT '진행중'")
    if "original_title" not in columns:
        conn.execute("ALTER TABLE plans ADD COLUMN original_title TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE plans SET original_title = title WHERE original_title = '' OR original_title IS NULL")
    if "original_priority" not in columns:
        conn.execute("ALTER TABLE plans ADD COLUMN original_priority TEXT NOT NULL DEFAULT '1순위'")
    if "current_priority" not in columns:
        conn.execute("ALTER TABLE plans ADD COLUMN current_priority TEXT NOT NULL DEFAULT '1순위'")
    if "tags" not in columns:
        conn.execute("ALTER TABLE plans ADD COLUMN tags TEXT NOT NULL DEFAULT ''")

    # plan_history 테이블 컬럼 호환성 유지
    cursor_hist = conn.execute("PRAGMA table_info(plan_history)")
    hist_cols = [row["name"] for row in cursor_hist.fetchall()]
    if "tags" not in hist_cols:
        conn.execute("ALTER TABLE plan_history ADD COLUMN tags TEXT NOT NULL DEFAULT ''")

    # 기존 '높음', '보통', '낮음' 우선순위를 '1순위', '2순위'... 형식으로 마이그레이션
    cursor = conn.execute("SELECT id, original_priority, current_priority FROM plans ORDER BY id ASC")
    rows = cursor.fetchall()
    for idx, row in enumerate(rows, start=1):
        orig_p = row["original_priority"]
        curr_p = row["current_priority"]
        updates = []
        params = []
        if orig_p in ["높음", "보통", "낮음"]:
            updates.append("original_priority = ?")
            params.append(f"{idx}순위")
        if curr_p in ["높음", "보통", "낮음"]:
            updates.append("current_priority = ?")
            params.append(f"{idx}순위")
        if updates:
            params.append(row["id"])
            conn.execute(f"UPDATE plans SET {', '.join(updates)} WHERE id = ?", params)

    # 기존 데이터 중 수정된 이력이 있으나 plan_history가 비어있는 경우 마이그레이션
    hist_cnt_row = conn.execute("SELECT COUNT(*) AS cnt FROM plan_history").fetchone()
    if hist_cnt_row and hist_cnt_row["cnt"] == 0:
        for row in rows:
            plan_row = conn.execute("SELECT * FROM plans WHERE id = ?", (row["id"],)).fetchone()
            if plan_row and (plan_row["updated_at"] != plan_row["created_at"] or (plan_row["original_title"] and plan_row["original_title"] != plan_row["title"])):
                conn.execute("""
                    INSERT INTO plan_history (
                        plan_id, version, title, priority,
                        start_date, end_date, success_criteria,
                        expected_minutes, status, modified_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    plan_row["id"],
                    1,
                    plan_row["original_title"] or plan_row["title"],
                    plan_row["original_priority"] or plan_row["current_priority"],
                    plan_row["original_start_date"] or plan_row["current_start_date"],
                    plan_row["original_end_date"] or plan_row["current_end_date"],
                    plan_row["original_success_criteria"] or plan_row["current_success_criteria"],
                    plan_row["original_expected_minutes"] or plan_row["current_expected_minutes"],
                    plan_row["status"],
                    plan_row["updated_at"]
                ))

    conn.commit()
    conn.close()


@app.route("/")
def index():
    return render_template("index.html")


# 모든 저장된 계획 목록 가져오기 (검색, 필터링, 정렬 지원)
@app.route("/api/plans", methods=["GET"])
def get_plans():
    query = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip()
    priority_filter = request.args.get("priority", "").strip()
    tag_filter = request.args.get("tag", "").strip()
    sort_by = request.args.get("sort", "priority-asc").strip()

    conn = get_db()

    sql = """
        SELECT p.*,
               (SELECT COUNT(*) FROM plan_history h WHERE h.plan_id = p.id) AS history_count
        FROM plans p
        WHERE 1=1
    """
    params = []

    if query:
        sql += " AND (p.title LIKE ? OR p.tags LIKE ? OR p.current_success_criteria LIKE ?)"
        q_wild = f"%{query}%"
        params.extend([q_wild, q_wild, q_wild])

    if status_filter and status_filter != "all":
        sql += " AND p.status = ?"
        params.append(status_filter)

    if priority_filter and priority_filter != "all":
        sql += " AND p.current_priority = ?"
        params.append(priority_filter)

    if tag_filter and tag_filter != "all":
        sql += " AND p.tags LIKE ?"
        params.append(f"%{tag_filter}%")

    if sort_by == "date-desc":
        sql += " ORDER BY p.id DESC"
    elif sort_by == "due-asc":
        sql += " ORDER BY p.current_end_date ASC, p.id DESC"
    elif sort_by == "time-asc":
        sql += " ORDER BY p.current_expected_minutes ASC, p.id DESC"
    else:  # priority-asc (기본)
        sql += """
            ORDER BY
                CASE
                    WHEN p.current_priority LIKE '%순위' THEN CAST(REPLACE(p.current_priority, '순위', '') AS INTEGER)
                    ELSE 999999
                END ASC,
                p.id DESC
        """

    cursor = conn.execute(sql, params)
    plans = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return jsonify({
        "plans": plans,
        "count": len(plans)
    })


# 특정 계획 또는 최신 계획 가져오기
@app.route("/api/plan", methods=["GET"])
def get_plan():
    plan_id = request.args.get("id")
    conn = get_db()

    if plan_id:
        try:
            plan = conn.execute("SELECT * FROM plans WHERE id = ?", (int(plan_id),)).fetchone()
        except (ValueError, TypeError):
            plan = None
    else:
        plan = conn.execute("""
            SELECT *
            FROM plans
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

    if plan is None:
        conn.close()
        return jsonify({
            "exists": False
        })

    plan_dict = dict(plan)

    # 수정 이력(plan_history)도 함께 반환
    hist_cursor = conn.execute("""
        SELECT *
        FROM plan_history
        WHERE plan_id = ?
        ORDER BY version DESC, id DESC
    """, (plan_dict["id"],))
    history = [dict(row) for row in hist_cursor.fetchall()]

    conn.close()

    return jsonify({
        "exists": True,
        "plan": plan_dict,
        "history": history
    })


# 최초 계획 저장
@app.route("/api/plan", methods=["POST"])
def create_plan():
    data = request.get_json()

    title = data.get("title", "").strip()
    priority = data.get("priority", "").strip()
    start_date = data.get("start_date", "")
    end_date = data.get("end_date", "")
    success_criteria = data.get("success_criteria", "").strip()

    try:
        expected_minutes = int(data.get("expected_minutes", 0))
    except (ValueError, TypeError):
        expected_minutes = 0

    # 입력 검증
    if not title:
        return jsonify({
            "success": False,
            "message": "계획을 입력해주세요."
        }), 400

    if not start_date or not end_date:
        return jsonify({
            "success": False,
            "message": "기간을 입력해주세요."
        }), 400

    if start_date > end_date:
        return jsonify({
            "success": False,
            "message": "시작일은 종료일보다 늦을 수 없습니다."
        }), 400

    if not success_criteria:
        return jsonify({
            "success": False,
            "message": "성공 기준을 입력해주세요."
        }), 400

    if expected_minutes <= 0:
        return jsonify({
            "success": False,
            "message": "예상 시간은 1분 이상 입력해주세요."
        }), 400

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    tags = data.get("tags", "").strip()

    conn = get_db()

    # 우선순위가 비어있거나 '보통'/'높음'/'낮음'인 경우 다음 순위로 자동 배정
    if not priority or priority in ["높음", "보통", "낮음"]:
        cnt_row = conn.execute("SELECT COUNT(*) AS cnt FROM plans").fetchone()
        count = cnt_row["cnt"] if cnt_row else 0
        priority = f"{count + 1}순위"

    # 최초 계획과 현재 계획을 같은 값으로 저장
    cursor = conn.execute("""
        INSERT INTO plans (
            title,
            tags,
            original_title,

            original_priority,
            original_start_date,
            original_end_date,
            original_success_criteria,
            original_expected_minutes,

            current_priority,
            current_start_date,
            current_end_date,
            current_success_criteria,
            current_expected_minutes,

            status,

            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        title,
        tags,
        title,

        priority,
        start_date,
        end_date,
        success_criteria,
        expected_minutes,

        priority,
        start_date,
        end_date,
        success_criteria,
        expected_minutes,

        "진행중",

        now,
        now
    ))

    conn.commit()

    plan_id = cursor.lastrowid

    conn.close()

    return jsonify({
        "success": True,
        "message": "계획이 저장되었습니다.",
        "plan_id": plan_id
    })


# 현재 계획 수정
@app.route("/api/plan", methods=["PUT"])
def update_plan():
    data = request.get_json()

    try:
        plan_id = int(data.get("id"))
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "message": "잘못된 계획입니다."
        }), 400

    title = data.get("title", "").strip()
    priority = data.get("priority", "").strip()
    start_date = data.get("start_date", "")
    end_date = data.get("end_date", "")
    success_criteria = data.get("success_criteria", "").strip()

    try:
        expected_minutes = int(data.get("expected_minutes", 0))
    except (ValueError, TypeError):
        expected_minutes = 0

    if not title:
        return jsonify({
            "success": False,
            "message": "계획을 입력해주세요."
        }), 400

    if not start_date or not end_date:
        return jsonify({
            "success": False,
            "message": "기간을 입력해주세요."
        }), 400

    if start_date > end_date:
        return jsonify({
            "success": False,
            "message": "시작일은 종료일보다 늦을 수 없습니다."
        }), 400

    if not success_criteria:
        return jsonify({
            "success": False,
            "message": "성공 기준을 입력하세요."
        }), 400

    if expected_minutes <= 0:
        return jsonify({
            "success": False,
            "message": "예상 시간은 1분 이상 입력해주세요."
        }), 400

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tags = data.get("tags", "").strip()

    conn = get_db()

    # 기존 계획 조회 (수정 전 상태)
    existing = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
    if not existing:
        conn.close()
        return jsonify({
            "success": False,
            "message": "계획을 찾을 수 없습니다."
        }), 404

    # 우선순위가 비어있거나 구버전 값인 경우 기존 우선순위 유지
    if not priority or priority in ["높음", "보통", "낮음"]:
        if existing["current_priority"]:
            priority = existing["current_priority"]
        else:
            priority = "1순위"

    # [T06-C08] 계획을 고쳐도 고치기 전 계획이 그대로 남아 있다.
    # 수정 전 계획 상태를 별도 표(plan_history)에 분리 저장하고, 계획 ID는 유지
    ver_cursor = conn.execute("SELECT COUNT(*) AS cnt FROM plan_history WHERE plan_id = ?", (plan_id,))
    ver_count = ver_cursor.fetchone()["cnt"]
    next_ver = ver_count + 1

    existing_tags = existing["tags"] if "tags" in existing.keys() else ""

    conn.execute("""
        INSERT INTO plan_history (
            plan_id,
            version,
            title,
            tags,
            priority,
            start_date,
            end_date,
            success_criteria,
            expected_minutes,
            status,
            modified_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        plan_id,
        next_ver,
        existing["title"],
        existing_tags,
        existing["current_priority"],
        existing["current_start_date"],
        existing["current_end_date"],
        existing["current_success_criteria"],
        existing["current_expected_minutes"],
        existing["status"],
        now
    ))

    result = conn.execute("""
        UPDATE plans
        SET
            title = ?,
            tags = ?,
            current_priority = ?,
            current_start_date = ?,
            current_end_date = ?,
            current_success_criteria = ?,
            current_expected_minutes = ?,
            updated_at = ?
        WHERE id = ?
    """, (
        title,
        tags,
        priority,
        start_date,
        end_date,
        success_criteria,
        expected_minutes,
        now,
        plan_id
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "계획이 수정되었습니다. 수정 전 계획은 이력 표에 보존됩니다."
    })


# 특정 계획의 수정 이력 목록 가져오기 (T06-C08)
@app.route("/api/plan/<int:plan_id>/history", methods=["GET"])
def get_plan_history(plan_id):
    conn = get_db()
    cursor = conn.execute("""
        SELECT *
        FROM plan_history
        WHERE plan_id = ?
        ORDER BY version DESC, id DESC
    """, (plan_id,))
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify({
        "success": True,
        "plan_id": plan_id,
        "history": history,
        "count": len(history)
    })


# 특정 수정 이력으로 계획 복원하기
@app.route("/api/plan/<int:plan_id>/history/<int:history_id>/restore", methods=["POST"])
def restore_plan_history(plan_id, history_id):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()

    target_history = conn.execute(
        "SELECT * FROM plan_history WHERE id = ? AND plan_id = ?",
        (history_id, plan_id)
    ).fetchone()

    if not target_history:
        conn.close()
        return jsonify({"success": False, "message": "해당 수정 이력을 찾을 수 없습니다."}), 404

    current = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
    if not current:
        conn.close()
        return jsonify({"success": False, "message": "계획을 찾을 수 없습니다."}), 404

    # 복원 전 현재 상태도 이력에 추가 보존
    ver_cursor = conn.execute("SELECT COUNT(*) AS cnt FROM plan_history WHERE plan_id = ?", (plan_id,))
    ver_count = ver_cursor.fetchone()["cnt"]
    next_ver = ver_count + 1

    current_tags = current["tags"] if "tags" in current.keys() else ""
    target_tags = target_history["tags"] if "tags" in target_history.keys() else ""

    conn.execute("""
        INSERT INTO plan_history (
            plan_id, version, title, tags, priority,
            start_date, end_date, success_criteria,
            expected_minutes, status, modified_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        plan_id, next_ver,
        current["title"], current_tags, current["current_priority"],
        current["current_start_date"], current["current_end_date"],
        current["current_success_criteria"], current["current_expected_minutes"],
        current["status"], now
    ))

    # 대상 이력 데이터로 plans 테이블 복원
    conn.execute("""
        UPDATE plans
        SET
            title = ?,
            tags = ?,
            current_priority = ?,
            current_start_date = ?,
            current_end_date = ?,
            current_success_criteria = ?,
            current_expected_minutes = ?,
            updated_at = ?
        WHERE id = ?
    """, (
        target_history["title"],
        target_tags,
        target_history["priority"],
        target_history["start_date"],
        target_history["end_date"],
        target_history["success_criteria"],
        target_history["expected_minutes"],
        now,
        plan_id
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": f"'{target_history['title']}'(v{target_history['version']}) 버전으로 계획이 복원되었습니다."
    })


# 계획 우선순위 일괄 변경 (드래그 앤 드롭 슬라이드 재정렬)
@app.route("/api/plans/reorder", methods=["PUT"])
def reorder_plans():
    data = request.get_json()
    order = data.get("order", [])

    if not isinstance(order, list) or len(order) == 0:
        return jsonify({
            "success": False,
            "message": "순서 데이터가 올바르지 않습니다."
        }), 400

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()

    # original_priority는 건드리지 않고 current_priority만 1순위, 2순위...로 변경하여 T06-C08 준수
    for rank, plan_id in enumerate(order, start=1):
        priority_str = f"{rank}순위"
        conn.execute("""
            UPDATE plans
            SET current_priority = ?, updated_at = ?
            WHERE id = ?
        """, (priority_str, now, int(plan_id)))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "우선순위가 성공적으로 변경되었습니다."
    })


# 계획 상태 변경 (진행중 <-> 완료)
# 완료로 변경 시 우선순위 맨 아래로 이동
@app.route("/api/plan/<int:plan_id>/status", methods=["PUT", "POST"])
def update_plan_status(plan_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")

    conn = get_db()
    current = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
    if not current:
        conn.close()
        return jsonify({"success": False, "message": "계획을 찾을 수 없습니다."}), 404

    # 상태 지정이 없으면 토글
    if not new_status:
        new_status = "완료" if current["status"] != "완료" else "진행중"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 전체 계획 ID를 현재 우선순위 순서대로 조회
    cursor = conn.execute("""
        SELECT id, status
        FROM plans
        ORDER BY
            CASE
                WHEN current_priority LIKE '%순위' THEN CAST(REPLACE(current_priority, '순위', '') AS INTEGER)
                ELSE 999999
            END ASC,
            id DESC
    """)
    all_rows = [dict(r) for r in cursor.fetchall()]

    plan_ids = [r["id"] for r in all_rows]
    if plan_id in plan_ids:
        plan_ids.remove(plan_id)

    if new_status == "완료":
        # 완료 상태로 변경되면 맨 아래로 이동
        plan_ids.append(plan_id)
    else:
        # 다시 진행중으로 바뀌면, 완료된 계획들 바로 앞으로 복귀
        completed_ids = [r["id"] for r in all_rows if r["id"] != plan_id and r["status"] == "완료"]
        if completed_ids:
            first_completed_idx = next((i for i, pid in enumerate(plan_ids) if pid in completed_ids), len(plan_ids))
            plan_ids.insert(first_completed_idx, plan_id)
        else:
            plan_ids.append(plan_id)

    # 모든 계획의 current_priority를 재할당 (1순위, 2순위, ...)
    for rank, pid in enumerate(plan_ids, start=1):
        if pid == plan_id:
            conn.execute("""
                UPDATE plans
                SET current_priority = ?, status = ?, updated_at = ?
                WHERE id = ?
            """, (f"{rank}순위", new_status, now, pid))
        else:
            conn.execute("""
                UPDATE plans
                SET current_priority = ?, updated_at = ?
                WHERE id = ?
            """, (f"{rank}순위", now, pid))

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": f"계획이 '{new_status}' 상태로 변경되었습니다.",
        "status": new_status
    })


# 계획 삭제 (해당 계획의 수정 이력도 함께 삭제)
@app.route("/api/plan/<int:plan_id>", methods=["DELETE"])
def delete_plan(plan_id):
    conn = get_db()
    conn.execute("DELETE FROM plan_history WHERE plan_id = ?", (plan_id,))
    result = conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
    conn.commit()
    deleted = result.rowcount > 0
    conn.close()

    if not deleted:
        return jsonify({
            "success": False,
            "message": "계획을 찾을 수 없습니다."
        }), 404

    return jsonify({
        "success": True,
        "message": "계획과 수정 이력이 삭제되었습니다."
    })


if __name__ == "__main__":
    init_db()

    print("=" * 50)
    print("Plan → Do → See 시작")
    print("http://127.0.0.1:5000")
    print("=" * 50)

    app.run(debug=True)