const actCopy = {
  normal: {
    running: "Running the happy-path check...",
    done: "Happy-path check passed. The accidental assumption remains hidden.",
    dolly: "Rows delivered unchanged. Paws off.",
    lessonTitle: "The test passes. The query is still wrong.",
    lesson:
      "SQLite happened to return insertion order, so the app saw DELIVERED last. SQL never promised that order.",
    reportKicker: "RUN REPORT",
    reportTitle: "No fault was injected",
    systemStatus: "All systems operational",
  },
  dolly: {
    running: "Dolly has joined the delivery route...",
    done: "Resilience check failed. The customer saw an older status.",
    dolly: "Rows shuffled. Nobody approved this.",
    lessonTitle: "DogDB exposed the hidden ordering dependency.",
    lesson:
      "SHUFFLE changed only row order. The query succeeded, but the app interpreted the last row as the latest event.",
    reportKicker: "INCIDENT REPORT",
    reportTitle: "Silent corruption detected",
    systemStatus: "Silent corruption detected",
  },
  fixed: {
    running: "Applying an ordered manifest...",
    done: "Resilience check passed with SHUFFLE still enabled.",
    dolly: "Ordered manifest. No shuffling eligible.",
    lessonTitle: "The application changed, not the test conditions.",
    lesson:
      "ORDER BY sequence makes chronology explicit. DogDB keeps SHUFFLE at 1.0, but ordered queries are not eligible.",
    reportKicker: "FIX VERIFICATION",
    reportTitle: "The ordered query resisted the fault",
    systemStatus: "Manifest fix verified",
  },
};

const buttons = [...document.querySelectorAll(".act-button")];
const runState = document.querySelector("#run-state");
const shiftStatus = document.querySelector("#shift-status");
const systemStatus = document.querySelector("#system-status");
const sourceEvents = document.querySelector("#source-events");
const deliveredEvents = document.querySelector("#delivered-events");
const dollyStage = document.querySelector("#dolly-stage");
const dollyCaption = document.querySelector("#dolly-caption");
const trackerResult = document.querySelector("#tracker-result");
const orderProduct = document.querySelector("#order-product");
const lesson = document.querySelector("#lesson");
const report = document.querySelector("#technical-report");
const reportKicker = document.querySelector("#report-kicker");
const reportTitle = document.querySelector("#report-title");
const sqlCode = document.querySelector("#sql-code");
const eventReport = document.querySelector("#event-report");
const metaFaults = document.querySelector("#meta-faults");
const metaSeed = document.querySelector("#meta-seed");
const metaSession = document.querySelector("#meta-session");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

buttons.forEach((button) => {
  button.addEventListener("click", () => runAct(button.dataset.act, button));
});

async function runAct(act, selectedButton) {
  const copy = actCopy[act];
  setBusy(true);
  runState.textContent = copy.running;
  dollyStage.dataset.mode = act;
  dollyCaption.textContent = copy.dolly;
  clearResults();
  prepareReport();

  try {
    const response = await fetch(`/api/acts/${act}`, { method: "POST" });
    if (!response.ok) {
      throw new Error(`Tutorial request failed (${response.status})`);
    }
    const result = await response.json();
    shiftStatus.dataset.state = act;
    systemStatus.textContent = copy.systemStatus;
    orderProduct.textContent = result.product;
    renderSource(result.source_events);
    await renderDelivery(result.delivered_events, act);
    renderTracker(result);
    renderLesson(copy);
    renderReport(result, copy);
    runState.textContent = copy.done;
    completeAct(selectedButton);
  } catch (error) {
    console.error("Tutorial run failed", { act, error });
    shiftStatus.dataset.state = "error";
    systemStatus.textContent = "Tutorial run failed";
    orderProduct.textContent = "Bone Biscuit Refill";
    dollyCaption.textContent = "Delivery interrupted. No route result available.";
    runState.textContent = error.message;
    trackerResult.className = "tracker-result is-failed";
    trackerResult.querySelector("strong").textContent = "ERROR";
    trackerResult.querySelector("p").textContent = "The local tutorial could not complete this run.";
    lesson.querySelector("h2").textContent = "This act did not complete.";
    lesson.querySelector("p:last-child").textContent =
      "Try again. If the problem continues, reload the page and check the tutorial server.";
    renderReportError(error);
  } finally {
    setBusy(false);
  }
}

function clearResults() {
  sourceEvents.replaceChildren();
  deliveredEvents.replaceChildren();
  sourceEvents.classList.remove("empty-stack");
  deliveredEvents.classList.remove("empty-stack");
  trackerResult.className = "tracker-result is-waiting";
  trackerResult.querySelector("strong").textContent = "IN TRANSIT";
  trackerResult.querySelector("p").textContent = "Reading the delivered event sequence...";
}

function prepareReport() {
  reportKicker.textContent = "RUNNING";
  reportTitle.textContent = "Updating technical report...";
  sqlCode.textContent = "Waiting for this act to complete.";
  metaFaults.textContent = "-";
  metaSeed.textContent = "-";
  metaSession.textContent = "-";

  const pending = document.createElement("p");
  pending.className = "quiet-event";
  pending.textContent = "Collecting DogDB events...";
  eventReport.replaceChildren(pending);
}

function renderReportError(error) {
  reportKicker.textContent = "RUN ERROR";
  reportTitle.textContent = "Technical report unavailable";
  sqlCode.textContent = "The act did not complete.";
  metaFaults.textContent = "unavailable";
  metaSeed.textContent = "unavailable";
  metaSession.textContent = "unavailable";

  const failure = document.createElement("p");
  failure.textContent = error.message;
  eventReport.replaceChildren(failure);
}

function renderSource(events) {
  events.forEach((event) => sourceEvents.append(createEventCard(event)));
}

async function renderDelivery(events, act) {
  const delay = deliveryDelay(act);
  for (const event of events) {
    const card = createEventCard(event);
    card.classList.add("in-transit");
    deliveredEvents.append(card);
    if (delay) {
      await wait(delay);
    }
  }
}

function deliveryDelay(act) {
  if (reducedMotion.matches) {
    return 0;
  }

  if (act === "dolly") {
    return 280;
  }

  return 180;
}

function createEventCard(event) {
  const card = document.createElement("article");
  card.className = "event-card";

  const sequence = document.createElement("span");
  sequence.textContent = String(event.sequence).padStart(2, "0");

  const status = document.createElement("strong");
  status.textContent = event.status.replaceAll("_", " ");

  card.append(sequence, status);
  return card;
}

function renderTracker(result) {
  trackerResult.className = `tracker-result ${result.passed ? "is-passed" : "is-failed"}`;
  trackerResult.querySelector("strong").textContent = result.observed_status.replaceAll("_", " ");
  trackerResult.querySelector("p").textContent = result.passed
    ? "Customer view agrees with the recorded latest event."
    : `Expected ${result.expected_status.replaceAll("_", " ")}. The order appeared to move backward.`;
}

function renderLesson(copy) {
  lesson.querySelector("h2").textContent = copy.lessonTitle;
  lesson.querySelector("p:last-child").textContent = copy.lesson;
}

function renderReport(result, copy) {
  reportKicker.textContent = copy.reportKicker;
  reportTitle.textContent = copy.reportTitle;
  sqlCode.textContent = result.sql;
  metaFaults.textContent = Object.entries(result.faults)
    .map(([fault, weight]) => `${fault}=${Number(weight).toFixed(1)}`)
    .join(", ") || "none";
  metaSeed.textContent = result.seed;
  metaSession.textContent = result.session_id;
  eventReport.replaceChildren();

  if (!result.events.length) {
    const quiet = document.createElement("p");
    quiet.className = "quiet-event";
    quiet.textContent = result.act === "fixed"
      ? "No event: top-level ORDER BY makes SHUFFLE ineligible."
      : "No fault event: every configured weight is zero.";
    eventReport.append(quiet);
    return;
  }

  const event = result.events[0];
  const fields = [
    ["fault", event.fault],
    ["category", event.category],
    ["severity", event.severity],
    ["outcome", event.outcome],
    ["phase", event.phase],
    ["occurrence", event.occurrence],
    ["event_id", event.event_id],
  ];
  const list = document.createElement("dl");
  fields.forEach(([name, value]) => {
    const row = document.createElement("div");
    const term = document.createElement("dt");
    const description = document.createElement("dd");
    term.textContent = name;
    description.textContent = value;
    row.append(term, description);
    list.append(row);
  });
  eventReport.append(list);
}

function completeAct(selectedButton) {
  buttons.forEach((button) => button.classList.remove("is-current"));
  selectedButton.classList.add("is-complete");
  const next = buttons.find((button) => !button.classList.contains("is-complete"));
  if (next) {
    next.disabled = false;
    next.classList.add("is-current");
  }
}

function setBusy(busy) {
  buttons.forEach((button) => {
    const unlocked = button.classList.contains("is-complete") || button.classList.contains("is-current");
    button.disabled = busy || !unlocked;
  });
  document.body.classList.toggle("is-running", busy);
}

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}
