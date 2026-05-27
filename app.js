const state = {
  items: [],
  dashboard: null,
  loading: false,
  dirty: false,
  scope: "current"
};

const list = document.querySelector("#list");
const message = document.querySelector("#message");
const summary = document.querySelector("#summary");
const statsBox = document.querySelector("#stats");
const checkFilter = document.querySelector("#checkFilter");
const statusFilter = document.querySelector("#statusFilter");
const verdictFilter = document.querySelector("#verdictFilter");
const refreshButton = document.querySelector("#refreshButton");
const template = document.querySelector("#anomalyTemplate");
const reviewersList = document.querySelector("#reviewersList");
const scopeTabs = document.querySelectorAll(".tab[data-scope]");
const CHECK_HELP = {};

const REVIEWERS = [
  "Иванов Сергей",
  "Фурсов Сергей",
  "Храмцевич Дмитрий",
  "Филюк Владимир",
  "Рыбак Николай",
  "Клименок Дмитрий",
  "Щепетов Артём",
  "Савкин Артём",
  "Власенко Максим",
  "Ливанцов Александр",
  "Кремлёв Владислав",
  "Мартынов Александр",
  "Мартынов Сергей",
  "Денисов Артём",
  "Игнатов Сергей",
  "Слуцкий Владимир",
  "Калоша Владислав",
  "Миронов Тимур",
  "Ромашевский Максим",
  "Кудлов Дмитрий",
  "Трофименков Роман",
  "Москвин Алексей",
  "Деркач Дмитрий",
  "Федоренко Александр",
  "Пиндюрин Владислав",
  "Карпов Дмитрий",
  "Гараев Ильдар",
  "Саликов Владимир",
  "Белоблодский Евгений",
  "Рушелюк Василий",
  "Пиванов Эдуард",
  "Кондратьев Андрей",
  "Лукъянец Кирилл",
  "Моглинцова Наталья",
  "Богомолов Вячеслав"
];

for (const reviewer of REVIEWERS) {
  const option = document.createElement("option");
  option.value = reviewer;
  reviewersList.appendChild(option);
}

Object.assign(CHECK_HELP, {
  period_deviations_average: {
    title: "Main = Period (average)",
    short: "Проверяет, совпадает ли общий тотал матча с суммой тоталов двух основных периодов.",
    long: "Для футбола берутся тоталы и индивидуальные тоталы с коэффициентами 1.65-2.30. Param усредняется по MainGameId, GameType, Period и EventType. Затем значение периода 0 сравнивается с суммой периодов 1 и 2. Критическая дельта зависит от размера общего тотала: до 5 = 1.0, до 10 = 1.5, до 20 = 2.0, до 35 = 2.0, выше 35 = 3.0."
  },
  total_deviations_average: {
    title: "Total = Ind total 1 + Ind Total 2 (average)",
    short: "Проверяет, согласован ли общий тотал с суммой индивидуальных тоталов команд.",
    long: "Для каждого периода и GameType выбирается линия с коэффициентом, ближайшим к 1.95. После этого общий Total сравнивается с IndTotal1 + IndTotal2. Аномалия появляется, если Total больше ожидаемой суммы более чем на 1.5."
  },
  stat_conflicts: {
    title: "Stat Conflicts",
    short: "Проверяет конфликт между фаворитом матча и фаворитом по статистическому рынку.",
    long: "Сначала определяется фаворит матча по рынкам p1/p2. Потом определяется фаворит по статистике: Corners, Tackles, ShotsOnTarget, ShotByGates, Save, GoalFromGates, PossessionPercentage. Если фавориты противоположны, строка считается аномалией. Для Save и GoalFromGates логика инвертирована."
  },
  football_stat_relations: {
    title: "Football Stat Relations",
    short: "Проверяет согласованность ударной статистики в футболе.",
    long: "Для Football period 0 центральный тотал выбирается как линия Total_B/Total_M с вероятностью ближе всего к 50%. Центральный тотал ShotsOnTarget не должен быть больше ShotByGates. Также фаворит ниже 1.8 по ShotsOnTarget или ShotByGates должен быть аутсайдером по GoalFromGates, потому что команда, которая больше бьет, обычно реже выполняет удары от ворот."
  },
  period_conflicts: {
    title: "Period Conflicts",
    short: "Проверяет, что фаворит матча остается тем же фаворитом в периодах.",
    long: "Для GameType Main сравниваются коэффициенты p1/p2 в периоде 0 и в отдельных периодах. Коэффициент ниже 1.8 считается фаворитом, 1.8-2.3 равной зоной, 2.3 и выше аутсайдером. Аномалия появляется, если фаворит периода отличается от фаворита матча."
  },
  tennis_special_what_earlear: {
    title: "Tennis Special. What Earlear",
    short: "Проверяет теннисную спецставку 'что раньше' против тоталов эйсов и брейков.",
    long: "Для тенниса сравниваются параметры Ace и Breaks с рынками ace_before_break и break_before_ace. Если тоталы указывают на один сценарий, а коэффициент рынка 'что раньше' выглядит противоположно, строка считается аномалией."
  }
});

function showMessage(text, isError = false) {
  message.hidden = !text;
  message.textContent = text || "";
  message.style.color = isError ? "#b42318" : "#65717e";
}

function fmtDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function fmtDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

function fmtNumber(value) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (Number.isNaN(number)) return value;
  return number.toLocaleString("ru-RU");
}

function oddsText(payload, prefix) {
  const p1 = payload[`${prefix}P1Coef`];
  const p2 = payload[`${prefix}P2Coef`];
  const z1 = payload[`${prefix}P1Zone`];
  const z2 = payload[`${prefix}P2Zone`];
  return `П1 ${p1 || "-"} (${z1 || "-"}) · П2 ${p2 || "-"} (${z2 || "-"})`;
}

function matchOddsText(payload) {
  if (payload.BaseP1Coef || payload.BaseP2Coef) return oddsText(payload, "Base");
  if (payload.MatchP1 || payload.MatchP2) {
    return `П1 ${payload.MatchP1 || "-"} (${payload.MatchP1Zone || "-"}) · П2 ${payload.MatchP2 || "-"} (${payload.MatchP2Zone || "-"})`;
  }
  if (payload.MatchCoefP1 || payload.MatchCoefP2) {
    return `П1 ${payload.MatchCoefP1 || "-"} · П2 ${payload.MatchCoefP2 || "-"}`;
  }
  return detailsText(payload);
}

function periodOddsText(payload) {
  if (payload.PeriodP1Coef || payload.PeriodP2Coef) return oddsText(payload, "Period");
  if (payload.PeriodP1 || payload.PeriodP2) {
    return `П1 ${payload.PeriodP1 || "-"} (${payload.PeriodP1Zone || "-"}) · П2 ${payload.PeriodP2 || "-"} (${payload.PeriodP2Zone || "-"})`;
  }
  if (payload.StatCoefP1 || payload.StatCoefP2) {
    return `П1 ${payload.StatCoefP1 || "-"} · П2 ${payload.StatCoefP2 || "-"}`;
  }
  return "";
}

function detailsText(payload) {
  const hidden = new Set([
    "Status", "Sport", "Champ", "Opp1", "Opp2", "Start",
    "MainGameId", "GameId", "GameType"
  ]);
  return Object.entries(payload)
    .filter(([key, value]) => !hidden.has(key) && value !== null && value !== undefined && value !== "")
    .map(([key, value]) => `${key}: ${value}`)
    .join(" · ");
}

function fillReview(form, item) {
  if (item.verdict) {
    const input = form.querySelector(`input[value="${item.verdict}"]`);
    if (input) input.checked = true;
  }
  form.review_comment.value = item.review_comment || "";
  form.reviewed_by.value = item.reviewed_by || "";
}

function applyReviewState(article, node, item) {
  const hasCompletedReview = Boolean(item.verdict);
  const stateBox = node.querySelector(".review-state");
  article.classList.remove("review-defect", "review-normal");

  if (!hasCompletedReview) {
    stateBox.textContent = "Новая";
    return;
  }

  if (item.verdict === "defect") {
    article.classList.add("review-defect");
    stateBox.textContent = `Defect · ${item.reviewed_by || "без проверяющего"}`;
  } else if (item.verdict === "normal") {
    article.classList.add("review-normal");
    stateBox.textContent = `Normal · ${item.reviewed_by || "без проверяющего"}`;
  }
}

async function saveReview(item, form, article) {
  const formData = new FormData(form);
  const verdict = formData.get("verdict");
  const reviewedBy = (formData.get("reviewed_by") || "").trim();
  if (!verdict) {
    showMessage("Выберите defect или normal", true);
    return;
  }
  if (!REVIEWERS.includes(reviewedBy)) {
    showMessage("Выберите проверяющего из списка", true);
    return;
  }
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    const response = await fetch("/api/review", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        result_key: item.result_key,
        verdict,
        review_comment: formData.get("review_comment"),
        reviewed_by: reviewedBy
      })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Save failed");
    article.classList.add("saved");
    state.dirty = false;
    showMessage("Сохранено");
    await loadAnomalies();
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    button.disabled = false;
  }
}

function valueOrDash(value) {
  return value === null || value === undefined || value === "" ? "-" : value;
}

function helpFor(item) {
  return CHECK_HELP[item.check_name] || Object.values(CHECK_HELP).find(help => help.title === item.check_title) || {
    title: item.check_title || item.check_name || "Anomaly",
    short: "Описание проверки еще не задано.",
    long: "Для этой проверки пока нет подробного описания."
  };
}

async function loadCheckDefinitions() {
  try {
    const response = await fetch("/check_definitions.json");
    if (!response.ok) return;
    const definitions = await response.json();
    for (const definition of definitions) {
      CHECK_HELP[definition.check_name] = {
        title: definition.check_title,
        short: definition.short_description,
        long: definition.full_description
      };
    }
  } catch {
    // Keep the built-in fallback definitions.
  }
}

function describeAnomaly(item) {
  const payload = item.payload_json || {};
  if (item.check_name === "period_conflicts") {
    return `В матче фаворит ${valueOrDash(payload.MatchFavorite)}, но в периоде ${valueOrDash(payload.Period)} фаворит ${valueOrDash(payload.PeriodFavorite)}. GameType: ${valueOrDash(payload.GameType)}.`;
  }
  if (item.check_name === "total_deviations_average") {
    return `Общий тотал ${valueOrDash(payload.Total)} не сходится с суммой индивидуальных тоталов ${valueOrDash(payload.IndTotal1)} + ${valueOrDash(payload.IndTotal2)} = ${valueOrDash(payload.Expected)}. Дельта: ${valueOrDash(payload.Delta)}.`;
  }
  if (item.check_name === "period_deviations_average") {
    const periods = String(payload.Periods || "1+2").split("+").filter(Boolean);
    const periodValues = periods.map(period => valueOrDash(payload[`P${period}`])).join(" + ");
    return `Значение периода 0 (${valueOrDash(payload.P0)}) сравнивается с суммой периодов ${periods.join("+")} (${periodValues}). Дельта: ${valueOrDash(payload.Delta)}, критический порог: ${valueOrDash(payload.CriticalDelta)}.`;
  }
  if (item.check_name === "stat_conflicts") {
    return `Фаворит матча ${valueOrDash(payload.MatchFavorite)}, а фаворит статистики ${valueOrDash(payload.StatType)} - ${valueOrDash(payload.StatFavorite)}. Это противоположные стороны.`;
  }
  if (item.check_name === "football_stat_relations") {
    return `${valueOrDash(payload.Rule)}. ${valueOrDash(payload.SourceGameType)} сравнивается с ${valueOrDash(payload.TargetGameType)}.`;
  }
  if (item.check_name === "tennis_special_what_earlear") {
    return `Тоталы Ace (${valueOrDash(payload.Param_Ace)}) и Breaks (${valueOrDash(payload.Param_Breaks)}) конфликтуют с коэффициентами рынка 'что раньше'.`;
  }
  return helpFor(item).short;
}

function marketLabel(payload) {
  const parts = [];
  if (payload.GameType) parts.push(`GameType ${payload.GameType}`);
  if (payload.EventType) parts.push(payload.EventType);
  if (payload.Type) parts.push(`Total ${payload.Type}`);
  if (payload.StatType) parts.push(payload.StatType);
  return parts.join(" · ") || "-";
}

function appendTable(container, columns, rows) {
  const table = document.createElement("table");
  table.className = "details-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const column of columns) {
    const th = document.createElement("th");
    th.textContent = column;
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const cell of row) {
      const td = document.createElement("td");
      td.textContent = valueOrDash(cell);
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  container.appendChild(table);
}

function renderDetails(container, item) {
  const payload = item.payload_json || {};
  container.querySelectorAll(".details-table").forEach(table => table.remove());
  container.classList.add("details-grid");

  if (item.check_name === "period_conflicts") {
    appendTable(container, ["GameType", "Period"], [
      [payload.GameType, payload.Period]
    ]);
    appendTable(container, ["Scope", "Favorite", "P1 coef", "P1 zone", "P2 coef", "P2 zone"], [
      ["Match", payload.MatchFavorite, payload.MatchP1, payload.MatchP1Zone, payload.MatchP2, payload.MatchP2Zone],
      [`Period ${valueOrDash(payload.Period)}`, payload.PeriodFavorite, payload.PeriodP1, payload.PeriodP1Zone, payload.PeriodP2, payload.PeriodP2Zone]
    ]);
  } else if (item.check_name === "total_deviations_average") {
    appendTable(container, ["GameType", "Event side", "Period", "Total", "Ind total 1", "Ind total 2", "Expected", "Delta"], [
      [payload.GameType, payload.Type, payload.Period, payload.Total, payload.IndTotal1, payload.IndTotal2, payload.Expected, payload.Delta]
    ]);
  } else if (item.check_name === "period_deviations_average") {
    const periods = String(payload.Periods || "1+2").split("+").filter(Boolean);
    appendTable(container, ["GameType", "EventType", "Main", ...periods.map(period => `Period ${period}`), "Delta", "Critical"], [
      [payload.GameType, payload.EventType, payload.P0, ...periods.map(period => payload[`P${period}`]), payload.Delta, payload.CriticalDelta]
    ]);
    appendTable(container, ["Game ID main", ...periods.map(period => `Game ID p${period}`)], [
      [payload.GID0, ...periods.map(period => payload[`GID${period}`])]
    ]);
  } else if (item.check_name === "stat_conflicts") {
    appendTable(container, ["Stat", "Match fav", "Stat fav", "Match P1", "Match P2", "Stat P1", "Stat P2"], [
      [payload.StatType, payload.MatchFavorite, payload.StatFavorite, payload.MatchCoefP1, payload.MatchCoefP2, payload.StatCoefP1, payload.StatCoefP2]
    ]);
  } else if (item.check_name === "football_stat_relations") {
    appendTable(container, ["Rule", "Source", "Target"], [
      [payload.Rule, payload.SourceGameType, payload.TargetGameType]
    ]);
    appendTable(container, ["Source game", "Target game", "Source P1", "Source P2", "Target P1", "Target P2"], [
      [payload.SourceGameId, payload.TargetGameId, payload.SourceCoefP1, payload.SourceCoefP2, payload.TargetCoefP1, payload.TargetCoefP2]
    ]);
    appendTable(container, ["Source center", "Target center", "Source coef", "Target coef"], [
      [payload.SourceCenterParam, payload.TargetCenterParam, payload.SourceCenterCoef, payload.TargetCenterCoef]
    ]);
  } else if (item.check_name === "tennis_special_what_earlear") {
    appendTable(container, ["Period", "Ace total", "Breaks total", "Ace before break", "Break before ace"], [
      [payload.Period, payload.Param_Ace, payload.Param_Breaks, payload.koef_ace_before_break, payload.koef_break_before_ace]
    ]);
  } else {
    const rows = Object.entries(payload)
      .filter(([, value]) => value !== null && value !== undefined && value !== "")
      .map(([key, value]) => [key, value]);
    appendTable(container, ["Field", "Value"], rows);
  }

  appendTable(container, ["MainGameId", "GameType", "EventType", "Occurrences"], [
    [payload.MainGameId || payload.GameId, payload.GameType, payload.EventType || payload.Type || payload.StatType, item.occurrence_count]
  ]);
}

function renderGuide() {
  list.textContent = "";
  showMessage("");
  summary.textContent = `${Object.keys(CHECK_HELP).length} описаний`;
  renderStats({ new: 0, defect: 0, normal: 0 });

  const guide = document.createElement("section");
  guide.className = "guide";
  for (const definition of Object.values(CHECK_HELP)) {
    const article = document.createElement("article");
    article.className = "guide-item";

    const title = document.createElement("h2");
    title.textContent = definition.title;
    article.appendChild(title);

    const short = document.createElement("p");
    short.className = "guide-short";
    short.textContent = definition.short;
    article.appendChild(short);

    const full = document.createElement("p");
    full.textContent = definition.long;
    article.appendChild(full);

    guide.appendChild(article);
  }
  list.appendChild(guide);
}

function dashboardMetric(label, value) {
  const node = document.createElement("div");
  node.className = "metric";

  const labelNode = document.createElement("div");
  labelNode.className = "metric-label";
  labelNode.textContent = label;
  node.appendChild(labelNode);

  const valueNode = document.createElement("div");
  valueNode.className = "metric-value";
  valueNode.textContent = value;
  node.appendChild(valueNode);

  return node;
}

function renderDashboard() {
  list.textContent = "";
  showMessage("");
  renderStats({ new: 0, defect: 0, normal: 0 });

  const data = state.dashboard || {};
  const latest = data.latest;
  const runs = data.runs || [];
  const checksByRun = data.checksByRun || {};
  summary.textContent = `${runs.length} runs · ${new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;

  if (!latest) {
    showMessage("Нет статистики прогонов");
    return;
  }

  const dashboard = document.createElement("section");
  dashboard.className = "dashboard";

  const metrics = document.createElement("div");
  metrics.className = "metrics";
  metrics.appendChild(dashboardMetric("Последний запуск", fmtDateTime(latest.started_at)));
  metrics.appendChild(dashboardMetric("Режим", latest.mode || "-"));
  metrics.appendChild(dashboardMetric("Выгружено строк", fmtNumber(latest.changed_games)));
  metrics.appendChild(dashboardMetric("Игр в снапшоте", fmtNumber(latest.snapshot_games)));
  metrics.appendChild(dashboardMetric("Аномалий", fmtNumber(latest.total_anomalies)));
  metrics.appendChild(dashboardMetric("Длительность, сек", fmtNumber(latest.duration_seconds)));
  dashboard.appendChild(metrics);

  const latestChecks = checksByRun[latest.run_id] || [];
  const checksSection = document.createElement("section");
  checksSection.className = "dashboard-section";
  const checksTitle = document.createElement("h2");
  checksTitle.textContent = "Последний прогон по проверкам";
  checksSection.appendChild(checksTitle);
  appendTable(
    checksSection,
    ["Проверка", "Аномалий", "Статусы", "Записано"],
    latestChecks.map(check => [
      check.check_title || check.check_name,
      check.rows_count,
      Object.entries(check.status_counts_json || {}).map(([key, value]) => `${key}: ${value}`).join(", ") || "-",
      check.synced_rows
    ])
  );
  dashboard.appendChild(checksSection);

  const runsSection = document.createElement("section");
  runsSection.className = "dashboard-section";
  const runsTitle = document.createElement("h2");
  runsTitle.textContent = "История запусков";
  runsSection.appendChild(runsTitle);
  appendTable(
    runsSection,
    ["Время", "Режим", "Выгружено", "Снапшот", "Аномалии", "Проверок с аномалиями", "Сек"],
    runs.map(run => [
      fmtDateTime(run.started_at),
      run.mode,
      run.changed_games,
      run.snapshot_games,
      run.total_anomalies,
      run.checks_with_anomalies,
      run.duration_seconds
    ])
  );
  dashboard.appendChild(runsSection);

  list.appendChild(dashboard);
}

function render() {
  if (state.scope === "guide") {
    renderGuide();
    return;
  }
  if (state.scope === "dashboard") {
    renderDashboard();
    return;
  }

  list.textContent = "";
  summary.textContent = `${state.items.length} записей · ${new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;

  if (!state.items.length) {
    showMessage("Нет записей под текущий фильтр");
    return;
  }
  showMessage("");

  for (const item of state.items) {
    const payload = item.payload_json || {};
    const node = template.content.cloneNode(true);
    const article = node.querySelector(".anomaly");
    const form = node.querySelector(".review");

    node.querySelector(".status").textContent = item.status;
    const help = helpFor(item);
    const titleNode = node.querySelector(".check-title");
    titleNode.textContent = item.check_title || item.check_name || "anomaly";
    titleNode.title = help.long;
    node.querySelector(".sport").textContent = payload.Sport || "";
    node.querySelector(".seen").textContent = `обновлено ${fmtDate(item.last_seen_at)}`;
    node.querySelector(".match").textContent = `${payload.Opp1 || "-"} vs ${payload.Opp2 || "-"}`;
    node.querySelector(".champ").textContent = payload.Champ || "";
    const description = document.createElement("div");
    description.className = "anomaly-description";
    description.textContent = describeAnomaly(item);
    node.querySelector(".anomaly-main").insertBefore(description, node.querySelector(".grid"));
    renderDetails(node.querySelector(".grid"), item);
    node.querySelector(".period-label").textContent = payload.Period ? `Период ${payload.Period}` : "Детали";
    node.querySelector(".meta").textContent = `MainGameId ${payload.MainGameId || payload.GameId || "-"} · GameType ${payload.GameType || "-"} · ${item.occurrence_count} раз`;

    fillReview(form, item);
    applyReviewState(article, node, item);
    form.addEventListener("input", () => {
      state.dirty = true;
    });
    form.addEventListener("submit", event => {
      event.preventDefault();
      saveReview(item, form, article);
    });

    list.appendChild(node);
  }
}

function renderStats(stats = {}) {
  statsBox.querySelector(".stat-new b").textContent = stats.new || 0;
  statsBox.querySelector(".stat-defect b").textContent = stats.defect || 0;
  statsBox.querySelector(".stat-normal b").textContent = stats.normal || 0;
}

function renderScopeTabs() {
  for (const tab of scopeTabs) {
    const active = tab.dataset.scope === state.scope;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
  }
}

async function loadAnomalies({ force = false } = {}) {
  if (state.loading) return;
  if (state.dirty && !force) return;
  if (state.scope === "guide") {
    renderGuide();
    return;
  }
  if (state.scope === "dashboard") {
    await loadDashboard();
    return;
  }
  state.loading = true;
  refreshButton.disabled = true;
  try {
    const params = new URLSearchParams({
      scope: state.scope,
      status: statusFilter.value,
      verdict: verdictFilter.value,
      check_title: checkFilter.value,
      limit: "200"
    });
    const response = await fetch(`/api/anomalies?${params}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Load failed");
    state.items = data.items || [];
    renderStats(data.stats || {});
    render();
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    state.loading = false;
    refreshButton.disabled = false;
  }
}

async function loadDashboard() {
  if (state.loading) return;
  state.loading = true;
  refreshButton.disabled = true;
  try {
    const response = await fetch("/api/dashboard?limit=20");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Load failed");
    state.dashboard = data;
    renderDashboard();
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    state.loading = false;
    refreshButton.disabled = false;
  }
}

refreshButton.addEventListener("click", () => {
  state.dirty = false;
  loadAnomalies({ force: true });
});
checkFilter.addEventListener("change", () => {
  state.dirty = false;
  loadAnomalies({ force: true });
});
statusFilter.addEventListener("change", () => {
  state.dirty = false;
  loadAnomalies({ force: true });
});
verdictFilter.addEventListener("change", () => {
  state.dirty = false;
  loadAnomalies({ force: true });
});
for (const tab of scopeTabs) {
  tab.addEventListener("click", () => {
    state.scope = tab.dataset.scope;
    state.dirty = false;
    renderScopeTabs();
    loadAnomalies({ force: true });
  });
}

async function boot() {
  await loadCheckDefinitions();
  renderScopeTabs();
  loadAnomalies();
}

boot();
setInterval(() => loadAnomalies(), 60000);
