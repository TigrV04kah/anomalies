const state = {
  items: [],
  dashboard: null,
  lineDashboard: null,
  loading: false,
  dirty: false,
  scope: "current",
  selectedLineSport: null,
  checkStats: {},
  checkStatsLoaded: false
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
const defaultReviewerInput = document.querySelector("#defaultReviewer");
const scopeTabs = document.querySelectorAll(".tab[data-scope]");
const CHECK_HELP = {};
const BASE_DOCUMENT_TITLE = document.title || "Line Monitor";
const DEFAULT_REVIEWER_STORAGE_KEY = "line-monitor-default-reviewer";
let previousCheckSelection = ["all"];

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

function storedReviewer() {
  try {
    return localStorage.getItem(DEFAULT_REVIEWER_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function saveStoredReviewer(value) {
  try {
    if (value) {
      localStorage.setItem(DEFAULT_REVIEWER_STORAGE_KEY, value);
    } else {
      localStorage.removeItem(DEFAULT_REVIEWER_STORAGE_KEY);
    }
  } catch {
    // Local storage can be unavailable in restricted browser modes.
  }
}

function defaultReviewer() {
  return (defaultReviewerInput?.value || storedReviewer()).trim();
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
    long: "Для каждого периода и GameType выбирается линия с коэффициентом, ближайшим к 1.95. Если выбранный коэффициент любой из трех нужных линий ниже 1.5 или выше 2.6, проверка по этой группе не выполняется. Исключение: Tennis/Ace для общего Total допускает коэффициент 2.4-2.7 и корректирует общий тотал для сравнения: Total_B - 1, Total_M + 1. После этого общий Total сравнивается с IndTotal1 + IndTotal2. Для индивидуальных тоталов Param корректируется к центральному: при коэффициенте 1.5-1.65 для IndTotal_B прибавляется 0.5, для IndTotal_M отнимается 0.5; при коэффициенте 2.3-2.6 корректировка обратная: для IndTotal_B отнимается 0.5, для IndTotal_M прибавляется 0.5. Волейбол period 0 исключен. Аномалия появляется, если абсолютная разница между Total и ожидаемой суммой выше динамического порога: <=5: 1.0, <=10: 1.5, <=20: 2.0, <=35: 2.0, <=60: 3.0, <=80: 4.0, <=120: 6.0, >120: 8.0. Для этого правила к базовому порогу добавляется 0.5. Для Rugby критический порог дополнительно увеличивается еще на 1.0."
  },
  stat_conflicts: {
    title: "Stat Conflicts",
    short: "Проверяет конфликт между фаворитом матча и фаворитом по статистическому рынку.",
    long: "Сначала определяется фаворит матча по рынкам p1/p2. Потом определяется фаворит по статистике: Corners, Tackles, ShotsOnTarget, ShotByGates, Save, GoalFromGates, PossessionPercentage. Если фавориты противоположны, строка считается аномалией. Для Save и GoalFromGates логика инвертирована."
  },
  individual_total_favorite_consistency: {
    title: "Individual Total Favorite Consistency",
    short: "Проверяет, что индивидуальный тотал больше фаворита согласован с индивидуальным тоталом аутсайдера.",
    long: "Для каждого GameID, где есть p1/p2 и IndTotal_1_B/IndTotal_2_B, определяется фаворит ниже 1.8. При одинаковом Param коэффициент фаворита должен быть ниже коэффициента аутсайдера. Если дельта вероятностей индивидуальных тоталов не выше 1.5 п.п. или один из коэффициентов ниже 1.1, сигнал сохраняется как SOFT и выводится только во вкладке Soft. Если одинакового Param нет, сравниваются центральные линии сторон: у каждой стороны берется Param с коэффициентом, ближайшим к вероятности 0.5. Центральный Param фаворита должен быть выше центрального Param аутсайдера. Для центрального сценария дельта Param до 0.5 при разнице вероятностей до 20 п.п. тоже считается SOFT."
  },
  football_stat_relations: {
    title: "Football Stat Relations",
    short: "Проверяет согласованность ударной статистики в футболе.",
    long: "Для Football period 0 центральный тотал выбирается как линия Total_B/Total_M с вероятностью ближе всего к 50%. Центральный тотал ShotsOnTarget не должен быть больше ShotByGates. Также фаворит ниже 1.8 по ShotsOnTarget или ShotByGates должен быть аутсайдером по GoalFromGates, потому что команда, которая больше бьет, обычно реже выполняет удары от ворот."
  },
  basketball_players: {
    title: "basketball players",
    short: "Проверяет баскетбольную статистику игроков: очки по периодам, монотонность тоталов и суммы составных рынков.",
    long: "Берутся только Basketball, GameType GoalPlayers и игроки, у которых есть тотал очков. Центральная линия выбирается по коэффициенту с вероятностью ближе всего к 50%. Для очков четверти 1-4 сравниваются с периодом 0 / 4, половины 11-12 - с периодом 0 / 2. Также проверяется монотонность тоталов больше/меньше с допуском 3% по вероятности для близких параметров и согласованность очки+подборы, очки+передачи, подборы+передачи, очки+подборы+передачи с отдельными компонентами."
  },
  basketball_q4_handicap_shift: {
    title: "Basketball Q4 Handicap Shift",
    short: "Проверяет, не слишком ли сильно фора 4-й четверти в баскетболе отличается от форы 1-й четверти.",
    long: "Для Basketball, GameType Main, рынков Fora_1 и Fora_2 берется центральная фора 1-й четверти по коэффициенту, ближайшему к 1.95. Если такой же параметр есть в 4-й четверти, сравниваются вероятности; разница больше 25 п.п. считается аномалией. Если такого параметра в 4-й четверти нет, сравниваются центральные параметры 1-й и 4-й четверти; разница больше 4.5 очка считается аномалией."
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

function fmtProbability(value) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (Number.isNaN(number)) return value;
  return `${(number * 100).toLocaleString("ru-RU", { maximumFractionDigits: 2 })}%`;
}

function coefWithProbability(coef, probability) {
  if (coef === null || coef === undefined || coef === "") return "-";
  const prob = probability !== undefined && probability !== null && probability !== ""
    ? probability
    : (Number(coef) > 0 ? 1 / Number(coef) : null);
  return `${valueOrDash(coef)} (${fmtProbability(prob)})`;
}

function lineValue(param, coef, probability, source) {
  const parts = [];
  if (param !== null && param !== undefined && param !== "") {
    parts.push(valueOrDash(param));
  }
  if (coef !== undefined || probability !== undefined) {
    parts.push(`coef ${coefWithProbability(coef, probability)}`);
  }
  if (source) parts.push(String(source));
  return parts.join(" · ");
}

function adjustedParamText(payload, prefix) {
  const original = payload[`${prefix}Original`] ?? payload[prefix];
  const adjusted = payload[`${prefix}Adjusted`] ?? payload[prefix];
  const adjustment = Number(payload[`${prefix}Adjustment`] || 0);
  if (!Number.isFinite(adjustment) || adjustment === 0) {
    return valueOrDash(adjusted);
  }
  const sign = adjustment > 0 ? "+" : "-";
  return `${valueOrDash(original)} ${sign} ${valueOrDash(Math.abs(adjustment))} = ${valueOrDash(adjusted)}`;
}

function totalSide(payload) {
  if (hasValue(payload.Type)) return String(payload.Type);
  const match = String(payload.EventType || "").match(/_(B|M)$/);
  return match ? match[1] : "";
}

function matchLineForSide(payload, side) {
  if (side !== "p1" && side !== "p2") return "-";
  const suffix = side === "p1" ? "P1" : "P2";
  return `${side} · ${lineValue("", payload[`MatchCoef${suffix}`], payload[`MatchProbability${suffix}`], payload[`MatchSource${suffix}`])}`;
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
  form.reviewed_by.value = item.reviewed_by || defaultReviewer();
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
  saveStoredReviewer(reviewedBy);
  if (defaultReviewerInput) {
    defaultReviewerInput.value = reviewedBy;
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

function appendSectionHeading(section, text) {
  const heading = document.createElement("h2");
  heading.textContent = text;
  section.appendChild(heading);
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

function checkFilterButtons() {
  return Array.from(checkFilter?.querySelectorAll(".check-filter-option") || []);
}

function currentCheckSelection() {
  return checkFilterButtons()
    .filter(button => button.classList.contains("active"))
    .map(button => button.dataset.value);
}

function selectedCheckTitles() {
  const selected = currentCheckSelection();
  if (!selected.length || selected.includes("all")) {
    return ["all"];
  }
  return selected;
}

function sortedCheckDefinitions() {
  return Object.values(CHECK_HELP)
    .filter(definition => definition?.title)
    .sort((left, right) => left.title.localeCompare(right.title, "ru", { sensitivity: "base" }));
}

function setCheckButtonActive(button, active) {
  button.classList.toggle("active", active);
  button.setAttribute("aria-pressed", active ? "true" : "false");
}

function updateCheckFilterButtons() {
  const selected = new Set(previousCheckSelection.length ? previousCheckSelection : ["all"]);
  for (const button of checkFilterButtons()) {
    setCheckButtonActive(button, selected.has(button.dataset.value));
  }
}

function normalizeCheckFilterSelection() {
  const available = new Set(checkFilterButtons().map(button => button.dataset.value));
  const selected = previousCheckSelection.filter(value => available.has(value));
  if (!selected.length || selected.includes("all")) {
    previousCheckSelection = ["all"];
  } else {
    previousCheckSelection = selected;
  }
  updateCheckFilterButtons();
}

function renderCheckFilter() {
  if (!checkFilter) return;
  checkFilter.textContent = "";
  const items = [
    { title: "\u0412\u0441\u0435", value: "all" },
    ...sortedCheckDefinitions().map(definition => ({
      title: definition.title,
      value: definition.title
    }))
  ];
  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "check-filter-option";
    button.dataset.value = item.value;
    const title = document.createElement("span");
    title.className = "check-filter-title";
    title.textContent = item.title;
    button.appendChild(title);
    const counter = document.createElement("span");
    counter.className = "check-filter-count";
    counter.textContent = String(state.checkStats[item.value]?.new || 0);
    counter.title = "Новые DIFF";
    button.appendChild(counter);
    button.title = `${item.title}: новых DIFF ${state.checkStats[item.value]?.new || 0}`;
    button.setAttribute("aria-pressed", "false");
    checkFilter.appendChild(button);
  }
  normalizeCheckFilterSelection();
}

function applyCheckFilterSelection(value) {
  if (value === "all") {
    previousCheckSelection = ["all"];
  } else {
    const selected = new Set(currentCheckSelection().filter(item => item !== "all"));
    if (selected.has(value)) {
      selected.delete(value);
    } else {
      selected.add(value);
    }
    previousCheckSelection = selected.size ? Array.from(selected) : ["all"];
  }
  updateCheckFilterButtons();
}

function isIndividualTotalFavoriteCheck(item) {
  return [
    "individual_total_favorite_consistency",
    "mathrobot_individual_total_favorite_consistency"
  ].includes(item.check_name);
}

function describeAnomaly(item) {
  const payload = item.payload_json || {};
  if (item.check_name === "period_conflicts") {
    return `В матче фаворит ${valueOrDash(payload.MatchFavorite)}, но в периоде ${valueOrDash(payload.Period)} фаворит ${valueOrDash(payload.PeriodFavorite)}. GameType: ${valueOrDash(payload.GameType)}.`;
  }
  if (item.check_name === "total_deviations_average") {
    const typeText = totalSide(payload) ? ` ${totalSide(payload)}` : "";
    return `Общий тотал${typeText} ${adjustedParamText(payload, "Total")} не сходится с расчетной суммой индивидуальных тоталов ${adjustedParamText(payload, "IndTotal1")} + ${adjustedParamText(payload, "IndTotal2")} = ${valueOrDash(payload.Expected)}. Дельта: ${valueOrDash(payload.Delta)}, |дельта|: ${valueOrDash(payload.AbsDelta ?? Math.abs(Number(payload.Delta)))}, критический порог: ${valueOrDash(payload.CriticalDelta)}.`;
  }
  if (item.check_name === "period_deviations_average") {
    const periods = String(payload.Periods || "1+2").split("+").filter(Boolean);
    const periodValues = periods.map(period => valueOrDash(payload[`P${period}`])).join(" + ");
    return `Значение периода 0 (${valueOrDash(payload.P0)}) сравнивается с суммой периодов ${periods.join("+")} (${periodValues}). Дельта: ${valueOrDash(payload.Delta)}, критический порог: ${valueOrDash(payload.CriticalDelta)}.`;
  }
  if (item.check_name === "stat_conflicts") {
    if (payload.ExpectedStatRole === "outsider") {
      return `Фаворит матча ${valueOrDash(payload.MatchFavorite)} должен быть аутсайдером по ${valueOrDash(payload.StatType)}, но коэффициент на него ниже коэффициента соперника.`;
    }
    return `Фаворит матча ${valueOrDash(payload.MatchFavorite)}, а фаворит статистики ${valueOrDash(payload.StatType)} - ${valueOrDash(payload.StatFavorite)}. Это противоположные стороны.`;
  }
  if (isIndividualTotalFavoriteCheck(item)) {
    const soft = payload.SoftReason ? ` Soft: ${payload.SoftReason}.` : "";
    if (payload.Scenario === "same_param_coef_direction") {
      return `На одинаковый индивидуальный тотал ${valueOrDash(payload.FavoriteParam)} коэффициент фаворита ${valueOrDash(payload.Favorite)} не ниже коэффициента аутсайдера ${valueOrDash(payload.Outsider)}. Дельта вероятностей: ${valueOrDash(payload.IndividualProbabilityDeltaPp)} п.п.${soft}`;
    }
    return `Одинакового Param нет, поэтому сравниваются центральные линии: фаворит ${valueOrDash(payload.Favorite)} (${valueOrDash(payload.FavoriteParam)}) не выше тотала аутсайдера ${valueOrDash(payload.Outsider)} (${valueOrDash(payload.OutsiderParam)}). Дельта Param: ${valueOrDash(payload.CentralParamAbsDelta)}, дельта вероятностей: ${valueOrDash(payload.CentralProbabilityDeltaPp)} п.п.${soft}`;
  }
  if (item.check_name === "football_stat_relations") {
    return `${valueOrDash(payload.Rule)}. ${valueOrDash(payload.SourceGameType)} сравнивается с ${valueOrDash(payload.TargetGameType)}.`;
  }
  if (item.check_name === "basketball_players") {
    return `${valueOrDash(payload.Rule)}. Игрок: ${valueOrDash(payload.Player)}, рынок: ${valueOrDash(payload.EventType || payload.Stat)}, период: ${valueOrDash(payload.Period)}.`;
  }
  if (item.check_name === "basketball_q4_handicap_shift") {
    if (payload.Scenario === "same_param_probability_delta") {
      return `В 1-й и 4-й четверти есть одинаковый параметр форы ${valueOrDash(payload.Q1Param)}, но разница вероятностей ${fmtNumber(Number(payload.AbsProbabilityDelta || 0) * 100)} п.п. выше порога 25 п.п.`;
    }
    return `В 4-й четверти нет центрального параметра 1-й четверти ${valueOrDash(payload.Q1Param)}. Центральная фора 4-й четверти ${valueOrDash(payload.Q4CentralParam)}, дельта ${valueOrDash(payload.AbsParamDelta)} выше порога 4.5.`;
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
  const wrapper = document.createElement("div");
  wrapper.className = "table-scroll";

  const table = document.createElement("table");
  table.className = "details-table";
  table.style.setProperty("--columns", String(columns.length));

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
  wrapper.appendChild(table);
  container.appendChild(wrapper);
}

function idRowsFromPayload(payload) {
  const rows = [];
  const seen = new Set();
  const add = (scope, gameType, eventType, period, gameId) => {
    if (gameId === null || gameId === undefined || gameId === "") return;
    const key = `${scope}|${gameType}|${eventType}|${period}|${gameId}`;
    if (seen.has(key)) return;
    seen.add(key);
    rows.push([scope, gameType || "-", eventType || "-", period || "-", gameId]);
  };

  const hasDetailedGameIds = [
    payload.TotalGameId,
    payload.IndTotal1GameId,
    payload.IndTotal2GameId,
    payload.MatchGameId,
    payload.PeriodGameId,
    payload.StatGameId,
    payload.FullGameId,
    payload.SourceGameId,
    payload.TargetGameId,
    payload.Q1GameId,
    payload.Q4CentralGameId,
    payload.Q4SameParamGameId,
    payload.FavoriteGameId,
    payload.OutsiderGameId,
  ].some(hasValue);

  add("MainGameID", payload.GameType, payload.EventType || payload.Type || payload.StatType, "-", payload.MainGameId);
  if (!hasDetailedGameIds) {
    add("GameID", payload.GameType, payload.EventType || payload.Type || payload.StatType, payload.Period, payload.GameId);
  }
  add("Match", payload.GameType || "Main", "p1/p2", 0, payload.MatchGameId);
  add("Period", payload.GameType || "Main", "p1/p2", payload.Period, payload.PeriodGameId);
  add("Stat", payload.GameType || payload.StatType, payload.StatType || "p1/p2", payload.Period, payload.StatGameId);
  add("Total", payload.GameType, `Total_${payload.Type || ""}`.replace(/_$/, ""), payload.Period, payload.TotalGameId);
  add("Ind total 1", payload.GameType, `IndTotal_1_${payload.Type || ""}`.replace(/_$/, ""), payload.Period, payload.IndTotal1GameId);
  add("Ind total 2", payload.GameType, `IndTotal_2_${payload.Type || ""}`.replace(/_$/, ""), payload.Period, payload.IndTotal2GameId);
  add("Full game", payload.GameType, payload.EventType, 0, payload.FullGameId);
  add("Source", payload.SourceGameType, payload.SourceCenterEventType || payload.EventType, "-", payload.SourceGameId);
  add("Target", payload.TargetGameType, payload.TargetCenterEventType || payload.EventType, "-", payload.TargetGameId);
  add("Q1", payload.GameType, payload.EventType, 1, payload.Q1GameId);
  add("Q4 center", payload.GameType, payload.EventType, 4, payload.Q4CentralGameId);
  add("Q4 same param", payload.GameType, payload.EventType, 4, payload.Q4SameParamGameId);
  add("Favorite ind total", payload.GameType, payload.FavoriteEventType, payload.Period, payload.FavoriteGameId);
  add("Outsider ind total", payload.GameType, payload.OutsiderEventType, payload.Period, payload.OutsiderGameId);

  Object.entries(payload).forEach(([key, value]) => {
    const match = key.match(/^GID(\d+)$/);
    if (match) {
      add(`Period ${match[1]}`, payload.GameType, payload.EventType, match[1], value);
    }
  });
  const handledGameIdKeys = new Set([
    "GameId",
    "MainGameId",
    "TotalGameId",
    "IndTotal1GameId",
    "IndTotal2GameId",
    "MatchGameId",
    "PeriodGameId",
    "StatGameId",
    "FullGameId",
    "SourceGameId",
    "TargetGameId",
    "Q1GameId",
    "Q4CentralGameId",
    "Q4SameParamGameId",
    "FavoriteGameId",
    "OutsiderGameId",
  ]);
  Object.entries(payload).forEach(([key, value]) => {
    if (handledGameIdKeys.has(key)) return;
    if (!key.endsWith("GameId") || key === "MainGameId" || key === "GameId") return;
    const scope = key.replace(/GameId$/, "").replace(/([a-z])([A-Z])/g, "$1 $2").trim();
    add(scope || "GameID", payload.GameType, payload.EventType || payload.Type || payload.StatType, payload.Period, value);
  });
  return rows;
}

function hasValue(value) {
  return value !== null && value !== undefined && value !== "";
}

function firstPresent(...values) {
  return values.find(hasValue);
}

function uniqueText(values) {
  return [...new Set(values.filter(hasValue).map(value => String(value)))];
}

function checkedPeriodText(payload, item) {
  if (hasValue(payload.Period)) return String(payload.Period);
  if (hasValue(payload.Periods)) return `0 vs ${payload.Periods}`;
  if (item.check_name === "basketball_q4_handicap_shift") return "1 vs 4";
  if (["stat_conflicts", "football_stat_relations", "tennis_special_what_earlear"].includes(item.check_name)) return "0";
  return "-";
}

function gameTypeText(payload) {
  const gameTypes = uniqueText([
    payload.GameType,
    payload.SourceGameType,
    payload.TargetGameType,
  ]);
  return gameTypes.length ? gameTypes.join(" / ") : "-";
}

function eventTypeText(payload, item) {
  if (hasValue(payload.EventTypes)) return payload.EventTypes;
  const eventTypes = uniqueText([
    payload.EventType,
    payload.FavoriteEventType,
    payload.OutsiderEventType,
    payload.SourceCenterEventType,
    payload.TargetCenterEventType,
    payload.StatType,
    payload.Type ? `Total_${payload.Type}` : null,
  ]);
  if (item.check_name === "total_deviations_average" && payload.Type) {
    return [`Total_${payload.Type}`, `IndTotal_1_${payload.Type}`, `IndTotal_2_${payload.Type}`].join(" / ");
  }
  return eventTypes.length ? eventTypes.join(" / ") : "-";
}

function gameIdText(payload) {
  const rows = idRowsFromPayload(payload).filter(row => row[0] !== "MainGameID");
  if (!rows.length) return "-";
  return rows
    .map(([scope, , , period, gameId]) => {
      const periodText = hasValue(period) && period !== "-" ? ` P${period}` : "";
      if (scope === "GameID") {
        return `${periodText.trim() || "GameID"}: ${gameId}`;
      }
      if (/^Period \d+$/.test(scope)) {
        return `${scope}: ${gameId}`;
      }
      return `${scope}${periodText}: ${gameId}`;
    })
    .join(" · ");
}

function renderCardMeta(container, item) {
  const payload = item.payload_json || {};
  const side = totalSide(payload);
  const meta = [
    ["Period", checkedPeriodText(payload, item)],
    ["MainGameID", payload.MainGameId || "-"],
    ["GameType", gameTypeText(payload)],
  ];
  if (side) {
    meta.push(["Type", side]);
  }
  const eventType = eventTypeText(payload, item);
  if (item.check_name !== "total_deviations_average" && eventType !== "-") {
    meta.push(["EventType", eventType]);
  }
  meta.push(
    ["GameID", gameIdText(payload)],
    ["Occurrences", item.occurrence_count || 0],
  );
  container.textContent = "";
  for (const [label, value] of meta) {
    const chip = document.createElement("span");
    chip.className = "meta-chip";
    const labelNode = document.createElement("b");
    labelNode.textContent = label;
    const valueNode = document.createElement("span");
    valueNode.textContent = valueOrDash(value);
    chip.append(labelNode, valueNode);
    container.appendChild(chip);
  }
}

function appendIdentityTables(container, payload, item) {
  appendTable(container, ["MainGameID", "GameType", "EventType", "Occurrences"], [
    [payload.MainGameId || payload.GameId, payload.GameType, payload.EventType || payload.Type || payload.StatType, item.occurrence_count]
  ]);
  const idRows = idRowsFromPayload(payload);
  if (idRows.length) {
    appendTable(container, ["Scope", "GameType", "EventType", "Period", "ID"], idRows);
  }
}

function compactCoef(coef, probability, source) {
  const parts = [];
  if (coef !== null && coef !== undefined && coef !== "") {
    const probabilityText = fmtProbability(probability);
    parts.push(`coef ${coef}${probabilityText ? ` (${probabilityText})` : ""}`);
  }
  if (source) parts.push(source);
  return parts.join(" · ");
}

function setSummary(container, details) {
  const normalized = [
    details[0] || {},
    details[1] || {},
    details[2] || {},
  ];
  const blocks = Array.from(container.children).filter(child => !child.classList.contains("table-scroll"));
  for (const [index, detail] of normalized.entries()) {
    const block = blocks[index];
    if (!block) continue;
    const label = block.querySelector(".label");
    const value = block.querySelector(index === 0 ? ".base-favorite" : index === 1 ? ".period-favorite" : ".key-value");
    const sub = block.querySelector(index === 0 ? ".base-odds" : index === 1 ? ".period-odds" : ".key-sub");
    if (label) label.textContent = detail.label || "-";
    if (value) value.textContent = valueOrDash(detail.value);
    if (sub) sub.textContent = valueOrDash(detail.sub);
  }
}

function summaryDetails(item) {
  const payload = item.payload_json || {};
  if (item.check_name === "total_deviations_average") {
    const side = totalSide(payload);
    return [
      {
        label: `${payload.Period ? `Период ${payload.Period}` : "Период 0"}${side ? ` · ${side}` : ""}`,
        value: `Total ${valueOrDash(payload.TotalOriginal ?? payload.Total)}`,
        sub: compactCoef(payload.TotalCoef, payload.TotalProbability, payload.TotalSource),
      },
      {
        label: "Ind 1 / Ind 2",
        value: `${valueOrDash(payload.IndTotal1Original ?? payload.IndTotal1)} + ${valueOrDash(payload.IndTotal2Original ?? payload.IndTotal2)}`,
        sub: [compactCoef(payload.IndTotal1Coef, payload.IndTotal1Probability), compactCoef(payload.IndTotal2Coef, payload.IndTotal2Probability)].filter(Boolean).join(" / "),
      },
      {
        label: "Ключ",
        value: `Expected ${valueOrDash(payload.Expected)}`,
        sub: `Δ ${valueOrDash(payload.Delta)} · |Δ| ${valueOrDash(payload.AbsDelta ?? Math.abs(Number(payload.Delta)))} · crit ${valueOrDash(payload.CriticalDelta)}`,
      },
    ];
  }
  if (item.check_name === "period_deviations_average") {
    const periods = String(payload.Periods || "1+2").split("+").filter(Boolean);
    return [
      {
        label: "Период 0",
        value: valueOrDash(payload.P0),
        sub: compactCoef(payload.P0Coef, payload.P0Probability, payload.P0Sources),
      },
      {
        label: periods.map(period => `P${period}`).join(" + ") || "Периоды",
        value: periods.map(period => valueOrDash(payload[`P${period}`])).join(" + "),
        sub: periods.map(period => compactCoef(payload[`P${period}Coef`], payload[`P${period}Probability`], payload[`P${period}Sources`])).filter(Boolean).join(" / "),
      },
      {
        label: "Ключ",
        value: `Δ ${valueOrDash(payload.Delta)}`,
        sub: `crit ${valueOrDash(payload.CriticalDelta)}`,
      },
    ];
  }
  if (item.check_name === "stat_conflicts") {
    return [
      {
        label: "Матч",
        value: valueOrDash(payload.MatchFavorite),
        sub: `P1 ${compactCoef(payload.MatchCoefP1, payload.MatchProbabilityP1)} · P2 ${compactCoef(payload.MatchCoefP2, payload.MatchProbabilityP2)}`,
      },
      {
        label: valueOrDash(payload.StatType),
        value: valueOrDash(payload.StatFavorite),
        sub: `P1 ${compactCoef(payload.StatCoefP1, payload.StatProbabilityP1)} · P2 ${compactCoef(payload.StatCoefP2, payload.StatProbabilityP2)}`,
      },
      {
        label: "Ключ",
        value: valueOrDash(payload.ExpectedStatRole),
        sub: "conflict",
      },
    ];
  }
  if (isIndividualTotalFavoriteCheck(item)) {
    return [
      {
        label: "Favorite",
        value: `${valueOrDash(payload.Favorite)} · ${valueOrDash(payload.FavoriteParam)}`,
        sub: compactCoef(payload.FavoriteCoef, payload.FavoriteProbability, payload.FavoriteSource),
      },
      {
        label: "Outsider",
        value: `${valueOrDash(payload.Outsider)} · ${valueOrDash(payload.OutsiderParam)}`,
        sub: compactCoef(payload.OutsiderCoef, payload.OutsiderProbability, payload.OutsiderSource),
      },
      {
        label: "Ключ",
        value: valueOrDash(payload.Scenario),
        sub: `Δ ${valueOrDash(payload.IndividualProbabilityDeltaPp || payload.CentralProbabilityDeltaPp)} p.p.`,
      },
    ];
  }
  if (item.check_name === "football_stat_relations") {
    return [
      {
        label: valueOrDash(payload.SourceGameType),
        value: valueOrDash(payload.SourceFavorite || payload.SourceCenterParam),
        sub: compactCoef(payload.SourceCenterCoef, payload.SourceCenterProbability, payload.SourceCenterSource),
      },
      {
        label: valueOrDash(payload.TargetGameType),
        value: valueOrDash(payload.TargetFavorite || payload.TargetCenterParam),
        sub: compactCoef(payload.TargetCenterCoef, payload.TargetCenterProbability, payload.TargetCenterSource),
      },
      {
        label: "Ключ",
        value: valueOrDash(payload.Rule),
        sub: `${valueOrDash(payload.SourceGameId)} → ${valueOrDash(payload.TargetGameId)}`,
      },
    ];
  }
  if (item.check_name === "basketball_players") {
    const hasLeftRight = hasValue(payload.LeftParam) || hasValue(payload.RightParam);
    const lineValueText = hasLeftRight
      ? `${valueOrDash(payload.LeftParam)} → ${valueOrDash(payload.RightParam)}`
      : valueOrDash(firstPresent(payload.CenterParam, payload.PeriodParam, payload.FullParam));
    const lineCoefText = hasLeftRight
      ? [
          compactCoef(payload.LeftCoef, payload.LeftProbability, payload.LeftSource),
          compactCoef(payload.RightCoef, payload.RightProbability, payload.RightSource)
        ].filter(Boolean).join(" → ")
      : compactCoef(
          firstPresent(payload.CenterCoef, payload.PeriodCoef, payload.FullCoef),
          firstPresent(payload.CenterProbability, payload.PeriodProbability, payload.FullProbability),
          firstPresent(payload.CenterSource, payload.PeriodSource, payload.FullSource)
        );
    return [
      {
        label: "Player",
        value: valueOrDash(payload.Player),
        sub: [payload.Stat, payload.EventType].filter(Boolean).join(" · "),
      },
      {
        label: "Line",
        value: lineValueText,
        sub: lineCoefText,
      },
      {
        label: "Ключ",
        value: valueOrDash(firstPresent(payload.Delta, payload.ParamDiff, payload.ExpectedParam)),
        sub: valueOrDash(payload.Rule),
      },
    ];
  }
  if (item.check_name === "basketball_q4_handicap_shift") {
    return [
      {
        label: "Q1",
        value: valueOrDash(payload.Q1Param),
        sub: compactCoef(payload.Q1Coef, payload.Q1Probability, payload.Q1Source),
      },
      {
        label: "Q4",
        value: valueOrDash(payload.Q4SameParam ?? payload.Q4CentralParam),
        sub: compactCoef(payload.Q4SameParamCoef ?? payload.Q4CentralCoef, payload.Q4SameParamProbability ?? payload.Q4CentralProbability, payload.Q4SameParamSource ?? payload.Q4CentralSource),
      },
      {
        label: "Ключ",
        value: valueOrDash(payload.Scenario),
        sub: `Δ ${valueOrDash(payload.AbsProbabilityDelta ?? payload.AbsParamDelta)}`,
      },
    ];
  }
  if (item.check_name === "period_conflicts") {
    return [
      {
        label: "Матч",
        value: valueOrDash(payload.MatchFavorite),
        sub: `P1 ${compactCoef(payload.MatchP1, payload.MatchProbabilityP1)} · P2 ${compactCoef(payload.MatchP2, payload.MatchProbabilityP2)}`,
      },
      {
        label: payload.Period ? `Период ${payload.Period}` : "Период",
        value: valueOrDash(payload.PeriodFavorite),
        sub: `P1 ${compactCoef(payload.PeriodP1, payload.PeriodProbabilityP1)} · P2 ${compactCoef(payload.PeriodP2, payload.PeriodProbabilityP2)}`,
      },
      {
        label: "Ключ",
        value: valueOrDash(payload.GameType),
        sub: `Δ ${valueOrDash(payload.PeriodProbabilityDelta)}`,
      },
    ];
  }
  if (item.check_name === "tennis_special_what_earlear") {
    return [
      { label: "Ace", value: valueOrDash(payload.Param_Ace), sub: valueOrDash(payload.koef_ace_before_break) },
      { label: "Breaks", value: valueOrDash(payload.Param_Breaks), sub: valueOrDash(payload.koef_break_before_ace) },
      { label: "Ключ", value: "what earlier", sub: payload.Period ? `Period ${payload.Period}` : "-" },
    ];
  }
  return [
    { label: "GameType", value: valueOrDash(payload.GameType), sub: valueOrDash(payload.EventType || payload.Type || payload.StatType) },
    { label: "Status", value: valueOrDash(item.status), sub: valueOrDash(item.check_name) },
    { label: "Ключ", value: valueOrDash(payload.MainGameId || payload.GameId), sub: `${valueOrDash(item.occurrence_count)} раз` },
  ];
}

function renderDetails(container, item) {
  const payload = item.payload_json || {};
  container.querySelectorAll(".table-scroll").forEach(node => node.remove());
  container.classList.remove("details-grid");
  setSummary(container, summaryDetails(item));
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

function renderHeatmap(hourly = []) {
  const wrapper = document.createElement("div");
  wrapper.className = "heatmap-stack";
  const sports = [...new Set(hourly.map(row => row.sport))].sort();
  const weekdays = [
    [1, "Пн"],
    [2, "Вт"],
    [3, "Ср"],
    [4, "Чт"],
    [5, "Пт"],
    [6, "Сб"],
    [7, "Вс"]
  ];

  for (const sport of sports) {
    const sportRows = hourly.filter(row => row.sport === sport);
    const byKey = new Map(sportRows.map(row => [`${row.weekday_local}|${row.hour_local}`, row]));
    const block = document.createElement("section");
    block.className = "heatmap-block";
    const title = document.createElement("h3");
    const sportAverage = sportRows[0]?.sport_average_main_games || 0;
    title.textContent = `${sport} · среднее ${fmtNumber(Math.round(sportAverage * 10) / 10)} MainGameID`;
    block.appendChild(title);

    const table = document.createElement("table");
    table.className = "heatmap-table";
    const thead = document.createElement("thead");
    const head = document.createElement("tr");
    ["День", ...Array.from({ length: 24 }, (_, hour) => String(hour).padStart(2, "0"))].forEach(label => {
      const th = document.createElement("th");
      th.textContent = label;
      head.appendChild(th);
    });
    thead.appendChild(head);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    for (const [weekday, label] of weekdays) {
      const tr = document.createElement("tr");
      const dayCell = document.createElement("th");
      dayCell.textContent = label;
      tr.appendChild(dayCell);
      for (let hour = 0; hour < 24; hour += 1) {
        const row = byKey.get(`${weekday}|${hour}`);
        const value = Number(row?.unique_main_games_avg) || 0;
        const relative = Math.min(2, Number(row?.relative_to_sport_average) || 0) / 2;
        const td = document.createElement("td");
        td.textContent = value ? fmtNumber(Math.round(value * 10) / 10) : "";
        td.title = `${sport}, ${label} ${String(hour).padStart(2, "0")}:00 · среднее MainGameID ${fmtNumber(Math.round(value * 10) / 10)} · прогонов ${fmtNumber(row?.samples || 0)}`;
        td.style.setProperty("--heat", String(relative));
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    block.appendChild(table);
    wrapper.appendChild(block);
  }
  return wrapper;
}

function renderSportRowsTable(container, rows) {
  const table = document.createElement("table");
  table.className = "details-table clickable-table";
  const columns = ["Sport", "MainGameID", "MainGameID + GameType", "EventType", "Game rows", "Events"];
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
    tr.tabIndex = 0;
    tr.className = row.sport === state.selectedLineSport ? "selected-row" : "";
    tr.title = "Нажмите, чтобы открыть GameType и heatmap";
    [row.sport, row.unique_main_games, row.unique_main_game_types, row.unique_event_types, row.games_count, row.events_count].forEach(value => {
      const td = document.createElement("td");
      td.textContent = valueOrDash(value);
      tr.appendChild(td);
    });
    tr.addEventListener("click", () => {
      state.selectedLineSport = state.selectedLineSport === row.sport ? null : row.sport;
      renderLineDashboard();
    });
    tr.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        tr.click();
      }
    });
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  container.appendChild(table);
}

function renderLineDashboard() {
  list.textContent = "";
  showMessage("");
  renderStats({ new: 0, defect: 0, normal: 0 });
  const data = state.lineDashboard || {};
  const latest = data.latest || {};
  summary.textContent = latest.run_id
    ? `Line Stats · ${fmtDateTime(latest.started_at)}`
    : "Line Stats";

  const dashboard = document.createElement("section");
  dashboard.className = "dashboard";
  if (!latest.run_id) {
    showMessage("Статистика линии еще не записана. Выполните SQL-миграцию и дождитесь следующего прогона.", true);
    list.appendChild(dashboard);
    return;
  }

  const metrics = document.createElement("div");
  metrics.className = "metrics";
  metrics.appendChild(dashboardMetric("Последний снимок", fmtDateTime(latest.started_at)));
  metrics.appendChild(dashboardMetric("Игр в снимке", fmtNumber(latest.snapshot_games)));
  metrics.appendChild(dashboardMetric("Спортов", fmtNumber((data.sport || []).length)));
  metrics.appendChild(dashboardMetric("SubSport", fmtNumber((data.subsport || []).length)));
  metrics.appendChild(dashboardMetric("Прогонов в heatmap", fmtNumber(data.historyRuns || 0)));
  dashboard.appendChild(metrics);

  const sportSection = document.createElement("section");
  sportSection.className = "dashboard-section";
  sportSection.innerHTML = "<h2>Топ-20 видов спорта</h2>";
  const topSports = (data.sport || []).slice(0, 20);
  if (state.selectedLineSport && !topSports.some(row => row.sport === state.selectedLineSport)) {
    state.selectedLineSport = null;
  }
  renderSportRowsTable(sportSection, topSports);
  dashboard.appendChild(sportSection);

  const subsportSection = document.createElement("section");
  subsportSection.className = "dashboard-section";
  subsportSection.innerHTML = "<h2>По SubSport</h2>";
  appendTable(
    subsportSection,
    ["SubSport", "MainGameID", "Game rows", "Events"],
    (data.subsport || []).map(row => [row.subsport, row.unique_main_games, row.games_count, row.events_count])
  );
  dashboard.appendChild(subsportSection);

  if (state.selectedLineSport) {
    const detailsSection = document.createElement("section");
    detailsSection.className = "dashboard-section";
    appendSectionHeading(detailsSection, `${state.selectedLineSport}: GameType`);
    appendTable(
      detailsSection,
      ["GameType", "MainGameID", "EventType", "Game rows", "Events"],
      (data.gameType || [])
        .filter(row => row.sport === state.selectedLineSport)
        .map(row => [row.game_type, row.unique_main_games, row.unique_event_types, row.games_count, row.events_count])
    );
    dashboard.appendChild(detailsSection);

    const heatmapSection = document.createElement("section");
    heatmapSection.className = "dashboard-section";
    appendSectionHeading(heatmapSection, `${state.selectedLineSport}: среднее по снимкам, день недели × час`);
    heatmapSection.appendChild(renderHeatmap((data.hourlyAverage || []).filter(row => row.sport === state.selectedLineSport)));
    dashboard.appendChild(heatmapSection);
  }

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
  if (state.scope === "line-dashboard") {
    renderLineDashboard();
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

    const statusNode = node.querySelector(".status");
    statusNode.textContent = item.status;
    statusNode.classList.toggle("status-soft", item.status === "SOFT");
    article.classList.toggle("soft-anomaly", item.status === "SOFT");
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
    renderCardMeta(node.querySelector(".card-meta"), item);

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

function updateDocumentTitle(activeDefectsCount) {
  const count = Number(activeDefectsCount) || 0;
  document.title = count > 0 ? `(${count}) ${BASE_DOCUMENT_TITLE}` : BASE_DOCUMENT_TITLE;
}

function renderScopeTabs() {
  for (const tab of scopeTabs) {
    const active = tab.dataset.scope === state.scope;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
  }
  statusFilter.disabled = state.scope === "soft";
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
  if (state.scope === "line-dashboard") {
    await loadLineDashboard();
    return;
  }
  state.loading = true;
  refreshButton.disabled = true;
  try {
    const params = new URLSearchParams({
      scope: state.scope,
      status: state.scope === "soft" ? "SOFT" : statusFilter.value,
      verdict: verdictFilter.value,
      limit: "200"
    });
    for (const title of selectedCheckTitles()) {
      params.append("check_title", title);
    }
    const response = await fetch(`/api/anomalies?${params}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Load failed");
    state.items = data.items || [];
    state.checkStats = data.check_stats || {};
    state.checkStatsLoaded = true;
    renderStats(data.stats || {});
    renderCheckFilter();
    if (state.scope === "current") {
      updateDocumentTitle(data.stats?.defect);
    }
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

async function loadLineDashboard() {
  if (state.loading) return;
  state.loading = true;
  refreshButton.disabled = true;
  try {
    const response = await fetch("/api/line-dashboard");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Load failed");
    state.lineDashboard = data;
    renderLineDashboard();
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
checkFilter?.addEventListener("click", event => {
  const button = event.target.closest(".check-filter-option");
  if (!button || !checkFilter.contains(button)) return;
  applyCheckFilterSelection(button.dataset.value);
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

if (defaultReviewerInput) {
  defaultReviewerInput.value = storedReviewer();
  defaultReviewerInput.addEventListener("change", () => {
    const reviewer = defaultReviewerInput.value.trim();
    if (reviewer && !REVIEWERS.includes(reviewer)) {
      showMessage("Выберите проверяющего из списка", true);
      return;
    }
    saveStoredReviewer(reviewer);
    document.querySelectorAll('form.review input[name="reviewed_by"]').forEach(input => {
      if (!input.value.trim()) {
        input.value = reviewer;
      }
    });
    showMessage(reviewer ? `Проверяющий сохранен: ${reviewer}` : "");
  });
}

async function boot() {
  await loadCheckDefinitions();
  renderCheckFilter();
  renderScopeTabs();
  loadAnomalies();
}

boot();
setInterval(() => loadAnomalies(), 60000);
