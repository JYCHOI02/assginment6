let allPlans = [];
let currentPlan = null;
let selectedPlanId = null;
let editing = false;
let isReorderMode = false;
let draggedIndex = null;

// HTML 요소
const form = document.getElementById("plan-form");
const formSection = document.getElementById("form-section");

const titleInput = document.getElementById("title");
const formPriorityDisplay = document.getElementById("form-priority-display");
const startDateInput = document.getElementById("start-date");
const endDateInput = document.getElementById("end-date");
const successCriteriaInput = document.getElementById("success-criteria");
const expectedMinutesInput = document.getElementById("expected-minutes");

const submitButton = document.getElementById("submit-button");
const cancelButton = document.getElementById("cancel-button");
const newPlanActionBtn = document.getElementById("new-plan-action-btn");
const newPlanFormBtn = document.getElementById("new-plan-form-btn");
const listNewPlanBtn = document.getElementById("list-new-plan-btn");

const formTitle = document.getElementById("form-title");
const modeText = document.getElementById("mode-text");

const planListSection = document.getElementById("plan-list-section");
const planListContainer = document.getElementById("plan-list");
const planCountSpan = document.getElementById("plan-count");
const reorderToggleBtn = document.getElementById("reorder-toggle-btn");
const reorderGuide = document.getElementById("reorder-guide");
const reorderDoneBtn = document.getElementById("reorder-done-btn");

const currentPlanSection = document.getElementById("current-plan-section");
const originalPlanSection = document.getElementById("original-plan-section");
const currentStatusBtn = document.getElementById("current-status-btn");
const displayStatusBadge = document.getElementById("display-status-badge");
const editButton = document.getElementById("edit-button");
const deleteButton = document.getElementById("delete-button");
const statusMessage = document.getElementById("status-message");

// 페이지 시작
document.addEventListener("DOMContentLoaded", loadPlans);

// 모든 저장된 계획 가져오기
async function loadPlans() {
    try {
        const response = await fetch("/api/plans");
        const data = await response.json();

        allPlans = data.plans || [];

        if (allPlans.length === 0) {
            currentPlan = null;
            selectedPlanId = null;
            planListSection.classList.add("hidden");
            currentPlanSection.classList.add("hidden");
            originalPlanSection.classList.add("hidden");
            showCreateMode();
            return;
        }

        // 계획이 있는 경우
        planListSection.classList.remove("hidden");
        planCountSpan.textContent = allPlans.length;

        // 이전에 선택된 계획이 유지되거나, 첫 번째 계획을 선택
        if (!selectedPlanId || !allPlans.some(p => p.id === selectedPlanId)) {
            selectedPlanId = allPlans[0].id;
        }

        currentPlan = allPlans.find(p => p.id === selectedPlanId) || allPlans[0];
        selectedPlanId = currentPlan.id;

        renderPlanList();
        displayPlan(currentPlan);

        currentPlanSection.classList.remove("hidden");
        originalPlanSection.classList.remove("hidden");

        if (!editing) {
            showViewMode();
        }

    } catch (error) {
        console.error(error);
        showStatus("서버와 연결할 수 없습니다.", "error");
    }
}

// 계획 목록 렌더링
function renderPlanList() {
    planListContainer.innerHTML = "";

    if (isReorderMode) {
        planListContainer.classList.add("reordering");
    } else {
        planListContainer.classList.remove("reordering");
    }

    allPlans.forEach((plan, index) => {
        const isCompleted = (plan.status === "완료");
        const item = document.createElement("div");
        item.className = `plan-item ${plan.id === selectedPlanId ? "active" : ""} ${isCompleted ? "completed" : ""}`;
        item.dataset.id = plan.id;
        item.dataset.index = index;

        // 우선순위 스타일 클래스
        const pVal = plan.current_priority || "1순위";
        let priorityClass = `plan-priority-${pVal}`;
        if (!["1순위", "2순위", "3순위"].includes(pVal)) {
            priorityClass = "plan-priority-rank";
        }

        item.innerHTML = `
            <div class="drag-handle" title="마우스로 클릭하여 위아래로 슬라이드(드래그)하세요">⠿</div>
            <div class="reorder-arrows">
                <button type="button" class="reorder-arrow-btn move-up" title="한 단계 위로 이동" ${index === 0 ? "disabled style='opacity:0.3;cursor:default;'" : ""}>▲</button>
                <button type="button" class="reorder-arrow-btn move-down" title="한 단계 아래로 이동" ${index === allPlans.length - 1 ? "disabled style='opacity:0.3;cursor:default;'" : ""}>▼</button>
            </div>
            <div class="plan-item-info">
                <div class="plan-item-header">
                    <span class="plan-item-title">${escapeHtml(plan.title)}</span>
                    <span class="plan-status-badge status-${isCompleted ? "완료" : "진행중"}">
                        ${isCompleted ? "완료" : "진행중"}
                    </span>
                    <span class="plan-priority-badge ${priorityClass}">${escapeHtml(pVal)}</span>
                </div>
                <div class="plan-item-meta">
                    <span>📅 ${escapeHtml(formatPeriod(plan.current_start_date, plan.current_end_date))}</span>
                    <span>⏱ ${escapeHtml(formatMinutes(plan.current_expected_minutes))}</span>
                </div>
            </div>
            <div class="plan-item-actions">
                ${isCompleted
                    ? `<button type="button" class="plan-revert-btn" title="이 계획을 다시 진행중으로 변경">↺ 다시 진행</button>`
                    : `<button type="button" class="plan-complete-btn" title="이 계획을 완료로 변경">✓ 완료하기</button>`
                }
                <button type="button" class="plan-select-btn">
                    ${plan.id === selectedPlanId ? "선택됨" : "보기"}
                </button>
                <button type="button" class="plan-delete-btn" title="계획 삭제">
                    삭제
                </button>
            </div>
        `;

        // 카드 클릭 시 선택 (재배치 모드가 아닐 때, 또는 상태/삭제/화살표 버튼이 아닐 때)
        item.onclick = (e) => {
            if (e.target.closest(".plan-delete-btn") ||
                e.target.closest(".reorder-arrow-btn") ||
                e.target.closest(".plan-complete-btn") ||
                e.target.closest(".plan-revert-btn")) {
                return;
            }
            if (isReorderMode && !e.target.closest(".plan-select-btn")) return;
            selectPlan(plan.id);
        };

        // 완료하기 / 다시 진행 버튼 이벤트
        const statusActionBtn = item.querySelector(".plan-complete-btn, .plan-revert-btn");
        if (statusActionBtn) {
            statusActionBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                togglePlanStatus(plan.id);
            });
        }

        // 삭제 버튼 이벤트
        const deleteBtn = item.querySelector(".plan-delete-btn");
        deleteBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            deletePlan(plan.id, plan.title);
        });

        // 위/아래 화살표 버튼 이벤트
        const moveUpBtn = item.querySelector(".move-up");
        const moveDownBtn = item.querySelector(".move-down");

        moveUpBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            if (index > 0) {
                movePlan(index, index - 1);
            }
        });

        moveDownBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            if (index < allPlans.length - 1) {
                movePlan(index, index + 1);
            }
        });

        // 드래그 앤 드롭 (슬라이드) 이벤트 설정
        if (isReorderMode) {
            item.setAttribute("draggable", "true");

            item.addEventListener("dragstart", (e) => {
                draggedIndex = index;
                item.classList.add("dragging");
                e.dataTransfer.effectAllowed = "move";
                e.dataTransfer.setData("text/plain", index);
            });

            item.addEventListener("dragover", (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
                item.classList.add("drag-over");
            });

            item.addEventListener("dragleave", () => {
                item.classList.remove("drag-over");
            });

            item.addEventListener("drop", (e) => {
                e.preventDefault();
                item.classList.remove("drag-over");
                if (draggedIndex !== null && draggedIndex !== index) {
                    movePlan(draggedIndex, index);
                }
            });

            item.addEventListener("dragend", () => {
                item.classList.remove("dragging");
                document.querySelectorAll(".drag-over").forEach(el => el.classList.remove("drag-over"));
                draggedIndex = null;
            });
        }

        planListContainer.appendChild(item);
    });
}

// 계획 상태 전환 (진행중 <-> 완료)
async function togglePlanStatus(id) {
    try {
        const response = await fetch(`/api/plan/${id}/status`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({})
        });
        const result = await response.json();

        if (!response.ok) {
            showStatus(result.message || "상태 변경 실패", "error");
            return;
        }

        showStatus(result.message, "success");
        await loadPlans();

    } catch (error) {
        console.error(error);
        showStatus("서버와 연결할 수 없습니다.", "error");
    }
}

// 계획 순서 이동 및 우선순위 갱신
async function movePlan(fromIndex, toIndex) {
    if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0 || fromIndex >= allPlans.length || toIndex >= allPlans.length) {
        return;
    }

    // 배열 내 위치 변경
    const moved = allPlans.splice(fromIndex, 1)[0];
    allPlans.splice(toIndex, 0, moved);

    // 우선순위 텍스트(1순위, 2순위...) 재할당
    allPlans.forEach((plan, idx) => {
        plan.current_priority = `${idx + 1}순위`;
    });

    renderPlanList();

    if (currentPlan) {
        displayPlan(currentPlan);
    }

    // 백엔드에 즉시 저장
    await savePriorityOrder();
}

// 우선순위 저장 API 호출
async function savePriorityOrder() {
    const order = allPlans.map(p => p.id);

    try {
        const response = await fetch("/api/plans/reorder", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ order })
        });

        const result = await response.json();

        if (!response.ok) {
            showStatus(result.message || "우선순위 저장 실패", "error");
            return;
        }

        showStatus("우선순위가 성공적으로 변경되었습니다.", "success");

    } catch (error) {
        console.error(error);
        showStatus("서버와 연결할 수 없습니다.", "error");
    }
}

// 우선순위 변경 모드 토글
function toggleReorderMode() {
    isReorderMode = !isReorderMode;

    if (isReorderMode) {
        reorderGuide.classList.remove("hidden");
        reorderToggleBtn.textContent = "✅ 변경 완료";
        reorderToggleBtn.className = "primary-button";
    } else {
        reorderGuide.classList.add("hidden");
        reorderToggleBtn.textContent = "🔄 우선순위 변경";
        reorderToggleBtn.className = "secondary-button";
    }

    renderPlanList();
}

// 특정 계획 선택
function selectPlan(id) {
    selectedPlanId = id;
    currentPlan = allPlans.find(p => p.id === id);

    if (currentPlan) {
        renderPlanList();
        displayPlan(currentPlan);

        if (editing) {
            showEditMode();
        } else {
            showViewMode();
        }
    }
}

// 계획 화면에 표시
function displayPlan(plan) {
    const status = plan.status || "진행중";
    const isCompleted = (status === "완료");

    // 상태 뱃지
    if (displayStatusBadge) {
        displayStatusBadge.textContent = status;
        displayStatusBadge.className = `plan-status-badge status-${status}`;
    }

    // 상태 전환 버튼
    if (currentStatusBtn) {
        if (isCompleted) {
            currentStatusBtn.textContent = "↺ 다시 진행중으로";
            currentStatusBtn.className = "status-toggle-btn is-completed";
        } else {
            currentStatusBtn.textContent = "✓ 완료하기";
            currentStatusBtn.className = "status-toggle-btn";
        }
    }

    // 현재 계획
    document.getElementById("display-title").textContent = plan.title;
    document.getElementById("display-priority").textContent = plan.current_priority || "1순위";
    document.getElementById("display-period").textContent = formatPeriod(
        plan.current_start_date,
        plan.current_end_date
    );
    document.getElementById("display-success").textContent = plan.current_success_criteria;
    document.getElementById("display-time").textContent = formatMinutes(plan.current_expected_minutes);
    document.getElementById("display-updated").textContent = plan.updated_at;

    // 처음 세운 계획 (수정 전 계획 보존)
    document.getElementById("original-title").textContent = plan.original_title || plan.title;
    document.getElementById("original-priority").textContent = plan.original_priority || "1순위";
    document.getElementById("original-period").textContent = formatPeriod(
        plan.original_start_date,
        plan.original_end_date
    );
    document.getElementById("original-success").textContent = plan.original_success_criteria;
    document.getElementById("original-time").textContent = formatMinutes(plan.original_expected_minutes);
}

// 기간 표시 포맷
function formatPeriod(start, end) {
    return `${start} ~ ${end}`;
}

// 분을 보기 좋게 표시
function formatMinutes(minutes) {
    const value = Number(minutes);

    if (value < 60) {
        return `${value}분`;
    }

    const hours = Math.floor(value / 60);
    const remainingMinutes = value % 60;

    if (remainingMinutes === 0) {
        return `${hours}시간`;
    }

    return `${hours}시간 ${remainingMinutes}분`;
}

// HTML 이스케이프 유틸
function escapeHtml(text) {
    if (!text) return "";
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// 새로운 계획 작성 모드
function showCreateMode() {
    editing = false;

    formTitle.textContent = "새 계획 작성";
    modeText.textContent = "새 계획";

    submitButton.textContent = "계획 저장";
    submitButton.classList.remove("hidden"); // 저장 버튼 활성화

    cancelButton.classList.add("hidden");
    newPlanFormBtn.classList.add("hidden");
    newPlanActionBtn.classList.add("hidden");

    form.reset();
    endDateInput.min = "";

    // 신규 작성 시 배정될 우선순위 표시
    const nextRank = allPlans.length + 1;
    formPriorityDisplay.textContent = `${nextRank}순위 (자동 배정)`;

    formSection.scrollIntoView({ behavior: "smooth" });
}

// 계획 보기 모드
function showViewMode() {
    editing = false;

    formTitle.textContent = "나의 계획";
    modeText.textContent = "저장됨";

    submitButton.classList.add("hidden");
    cancelButton.classList.add("hidden");

    newPlanFormBtn.classList.remove("hidden");
    newPlanActionBtn.classList.remove("hidden");

    if (currentPlan) {
        formPriorityDisplay.textContent = currentPlan.current_priority || "1순위";
    }
}

// 수정 모드
function showEditMode() {
    if (!currentPlan) return;

    editing = true;

    formTitle.textContent = `계획 수정: ${currentPlan.title}`;
    modeText.textContent = "수정 중";

    submitButton.textContent = "수정 저장";
    submitButton.classList.remove("hidden");
    cancelButton.classList.remove("hidden");

    newPlanFormBtn.classList.add("hidden");
    newPlanActionBtn.classList.add("hidden");

    // 현재 선택된 계획 값을 입력창에 채움
    titleInput.value = currentPlan.title;
    formPriorityDisplay.textContent = currentPlan.current_priority || "1순위";
    startDateInput.value = currentPlan.current_start_date;
    endDateInput.value = currentPlan.current_end_date;
    endDateInput.min = currentPlan.current_start_date;
    successCriteriaInput.value = currentPlan.current_success_criteria;
    expectedMinutesInput.value = currentPlan.current_expected_minutes;

    formSection.scrollIntoView({ behavior: "smooth" });
}

// 시작일 변경 시 종료일의 최소 날짜(min)를 시작일로 설정하여 과거 날짜 선택 방지
function updateEndDateMin() {
    if (startDateInput.value) {
        endDateInput.min = startDateInput.value;
        if (endDateInput.value && endDateInput.value < startDateInput.value) {
            endDateInput.value = startDateInput.value;
        }
    } else {
        endDateInput.min = "";
    }
}

startDateInput.addEventListener("input", updateEndDateMin);
startDateInput.addEventListener("change", updateEndDateMin);

endDateInput.addEventListener("change", function() {
    if (startDateInput.value && endDateInput.value && endDateInput.value < startDateInput.value) {
        showStatus("종료일은 시작일보다 빠를 수 없습니다.", "error");
        endDateInput.value = startDateInput.value;
    }
});

// 계획 저장 / 수정 전송
form.addEventListener("submit", async function(event) {
    event.preventDefault();

    const planData = {
        title: titleInput.value.trim(),
        start_date: startDateInput.value,
        end_date: endDateInput.value,
        success_criteria: successCriteriaInput.value.trim(),
        expected_minutes: Number(expectedMinutesInput.value)
    };

    if (!planData.title) {
        showStatus("계획을 입력해주세요.", "error");
        return;
    }

    if (!planData.start_date || !planData.end_date) {
        showStatus("기간을 입력해주세요.", "error");
        return;
    }

    if (planData.start_date > planData.end_date) {
        showStatus("시작일은 종료일보다 늦을 수 없습니다.", "error");
        return;
    }

    if (!planData.success_criteria) {
        showStatus("성공 기준을 입력해주세요.", "error");
        return;
    }

    if (!planData.expected_minutes || planData.expected_minutes <= 0) {
        showStatus("예상 시간을 입력해주세요.", "error");
        return;
    }

    try {
        let response;

        if (editing) {
            planData.id = currentPlan.id;
            planData.priority = currentPlan.current_priority;
            response = await fetch("/api/plan", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(planData)
            });
        } else {
            response = await fetch("/api/plan", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(planData)
            });
        }

        const result = await response.json();

        if (!response.ok) {
            showStatus(result.message || "저장에 실패했습니다.", "error");
            return;
        }

        showStatus(result.message, "success");

        if (!editing && result.plan_id) {
            selectedPlanId = result.plan_id;
        }

        editing = false;
        await loadPlans();

    } catch (error) {
        console.error(error);
        showStatus("서버와 연결할 수 없습니다.", "error");
    }
});

// 계획 삭제
async function deletePlan(id, title) {
    if (!confirm(`'${title}' 계획을 삭제하시겠습니까?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/plan/${id}`, {
            method: "DELETE"
        });
        const result = await response.json();

        if (!response.ok) {
            showStatus(result.message || "삭제에 실패했습니다.", "error");
            return;
        }

        showStatus(result.message, "success");

        if (selectedPlanId === id) {
            selectedPlanId = null;
        }

        await loadPlans();

        // 삭제 후 남은 계획들의 우선순위를 1순위, 2순위...로 재정렬 저장
        if (allPlans.length > 0) {
            allPlans.forEach((plan, idx) => {
                plan.current_priority = `${idx + 1}순위`;
            });
            await savePriorityOrder();
            renderPlanList();
        }

    } catch (error) {
        console.error(error);
        showStatus("서버와 연결할 수 없습니다.", "error");
    }
}

// 수정 버튼 이벤트
editButton.addEventListener("click", showEditMode);

// 상태 토글 버튼 이벤트 (현재 계획 상세 영역)
if (currentStatusBtn) {
    currentStatusBtn.addEventListener("click", () => {
        if (currentPlan) {
            togglePlanStatus(currentPlan.id);
        }
    });
}

// 삭제 버튼 이벤트 (현재 계획 영역의 삭제 버튼)
if (deleteButton) {
    deleteButton.addEventListener("click", () => {
        if (currentPlan) {
            deletePlan(currentPlan.id, currentPlan.title);
        }
    });
}

// 수정 취소
cancelButton.addEventListener("click", function() {
    if (currentPlan) {
        displayPlan(currentPlan);
        showViewMode();
    } else {
        showCreateMode();
    }
});

// 새 계획 작성 버튼 이벤트들
newPlanFormBtn.addEventListener("click", showCreateMode);
newPlanActionBtn.addEventListener("click", showCreateMode);
listNewPlanBtn.addEventListener("click", showCreateMode);

// 우선순위 변경 모드 버튼들
reorderToggleBtn.addEventListener("click", toggleReorderMode);
reorderDoneBtn.addEventListener("click", toggleReorderMode);

// 상태 메시지 표시
function showStatus(message, type = "") {
    statusMessage.textContent = message;
    statusMessage.className = "status";

    if (type) {
        statusMessage.classList.add(type);
    }

    setTimeout(function() {
        statusMessage.textContent = "";
        statusMessage.className = "status";
    }, 3000);
}