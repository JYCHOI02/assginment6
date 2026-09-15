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

    conn.commit()
    conn.close()


@app.route("/")
def index():
    return render_template("index.html")


# 모든 저장된 계획 목록 가져오기 (우선순위 오름차순: 1순위, 2순위, ...)
@app.route("/api/plans", methods=["GET"])
def get_plans():
    conn = get_db()

    cursor = conn.execute("""
        SELECT *
        FROM plans
        ORDER BY
            CASE
                WHEN current_priority LIKE '%순위' THEN CAST(REPLACE(current_priority, '순위', '') AS INTEGER)
                ELSE 999999
            END ASC,
            id DESC
    """)
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

    conn.close()

    if plan is None:
        return jsonify({
            "exists": False
        })

    return jsonify({
        "exists": True,
        "plan": dict(plan)
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        title,
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
            "message": "성공 기준을 입력해주세요."
        }), 400

    if expected_minutes <= 0:
        return jsonify({
            "success": False,
            "message": "예상 시간은 1분 이상 입력해주세요."
        }), 400

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()

    # 우선순위가 비어있거나 구버전 값인 경우 기존 우선순위 유지
    if not priority or priority in ["높음", "보통", "낮음"]:
        existing = conn.execute("SELECT current_priority FROM plans WHERE id = ?", (plan_id,)).fetchone()
        if existing and existing["current_priority"]:
            priority = existing["current_priority"]
        else:
            priority = "1순위"

    # original_* 컬럼은 유지하고 current_* 컬럼만 수정
    result = conn.execute("""
        UPDATE plans
        SET
            title = ?,
            current_priority = ?,
            current_start_date = ?,
            current_end_date = ?,
            current_success_criteria = ?,
            current_expected_minutes = ?,
            updated_at = ?
        WHERE id = ?
    """, (
        title,
        priority,
        start_date,
        end_date,
        success_criteria,
        expected_minutes,
        now,
        plan_id
    ))

    conn.commit()

    updated = result.rowcount > 0

    conn.close()

    if not updated:
        return jsonify({
            "success": False,
            "message": "계획을 찾을 수 없습니다."
        }), 404

    return jsonify({
        "success": True,
        "message": "계획이 수정되었습니다."
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


# 계획 삭제
@app.route("/api/plan/<int:plan_id>", methods=["DELETE"])
def delete_plan(plan_id):
    conn = get_db()
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
        "message": "계획이 삭제되었습니다."
    })


if __name__ == "__main__":
    init_db()

    print("=" * 50)
    print("Plan → Do → See 시작")
    print("http://127.0.0.1:5000")
    print("=" * 50)

    app.run(debug=True)