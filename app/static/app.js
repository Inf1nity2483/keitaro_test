const banner = document.querySelector("#banner");
const meta = document.querySelector("#meta");
const editor = document.querySelector("#editor");
const list = document.querySelector("#campaign-list");
let selectedOfferId = null;
let busy = false;

function showError(error) {
  banner.hidden = false;
  banner.textContent = error.message || String(error);
}

function clearError() {
  banner.hidden = true;
  banner.textContent = "";
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  let data = null;
  if (text) {
    try { data = JSON.parse(text); } catch { data = { detail: text }; }
  }
  if (!response.ok) {
    const message = data && data.detail ? data.detail : `Ошибка ${response.status}`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return data;
}

function bindSearch(input, box, onPick) {
  let timer = 0;
  async function run() {
    const query = input.value.trim();
    box.innerHTML = "";
    try {
      const rows = await api("/api/offers?q=" + encodeURIComponent(query));
      for (const row of rows) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = `[${row.id}] ${row.name}`;
        button.addEventListener("click", () => {
          input.value = `[${row.id}] ${row.name}`;
          onPick(row);
          box.innerHTML = "";
        });
        box.appendChild(button);
      }
    } catch (error) {
      showError(error);
    }
  }
  input.addEventListener("input", () => {
    onPick(null);
    clearTimeout(timer);
    timer = setTimeout(run, 200);
  });
  input.addEventListener("focus", () => {
    clearTimeout(timer);
    timer = setTimeout(run, 0);
  });
}

bindSearch(document.querySelector("#create-offer"), document.querySelector("#create-results"), (row) => {
  selectedOfferId = row ? row.id : null;
});

document.querySelector("#create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();
  if (!selectedOfferId) {
    showError(new Error("Выбери оффер из подсказки"));
    return;
  }
  const form = new FormData(event.target);
  await run(async () => {
    const data = await api("/api/campaigns", {
      method: "POST",
      body: JSON.stringify({
        name: form.get("name"),
        geo: form.get("geo"),
        offer_id: selectedOfferId,
      }),
    });
    renderEditor(data);
    await loadCampaigns();
  });
});

document.querySelector("#open-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = new FormData(event.target).get("keitaro_id");
  await fetchCampaign(id, true);
});

async function loadMeta() {
  try {
    const data = await api("/api/meta");
    meta.textContent = data.tracker;
    const problems = [];
    if (!data.key_set) problems.push("в .env пустой KEITARO_API_KEY");
    if (!data.prefix_ready) problems.push("CAMPAIGN_PREFIX должен быть вида test_фамилия_");
    if (problems.length) showError(new Error(problems.join(". ")));
    const name = document.querySelector("#create-form [name=name]");
    if (data.prefix_ready) name.placeholder = data.prefix + "campaign1";
  } catch (error) {
    showError(error);
  }
}

async function loadCampaigns() {
  const rows = await api("/api/campaigns");
  list.innerHTML = "";
  for (const row of rows) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${row.name} · #${row.keitaro_id}`;
    button.addEventListener("click", () => fetchCampaign(row.keitaro_id, false));
    item.appendChild(button);
    list.appendChild(item);
  }
}

async function fetchCampaign(id, fromKeitaro) {
  clearError();
  if (fromKeitaro && editor.querySelector(".stream.dirty")) {
    const agreed = window.confirm("Неопубликованные правки будут заменены данными из Keitaro.");
    if (!agreed) return;
  }
  await run(async () => {
    const path = fromKeitaro ? `/api/campaigns/${id}/fetch` : `/api/campaigns/${id}`;
    const data = await api(path, { method: fromKeitaro ? "POST" : "GET" });
    renderEditor(data);
    if (fromKeitaro) await loadCampaigns();
  });
}

function renderEditor(data) {
  editor.hidden = false;
  const campaign = data.campaign;
  editor.innerHTML = "";
  const board = document.createElement("article");
  board.className = "campaign-board";

  const head = document.createElement("div");
  head.className = "editor-head";
  const title = document.createElement("div");
  title.innerHTML = `<h2>${escapeHtml(campaign.name)}</h2><p class="quiet">#${campaign.keitaro_id}${campaign.url ? " · " + escapeHtml(campaign.url) : ""}</p><p class="quiet">${escapeHtml(campaign.domain || "домен не сохранён")} · ${escapeHtml(campaign.group_name || "группа")} · ${escapeHtml(campaign.source_name || "источник")}</p>`;
  const fetchButton = document.createElement("button");
  fetchButton.type = "button";
  fetchButton.className = "ghost";
  fetchButton.textContent = "Fetch streams";
  fetchButton.addEventListener("click", () => fetchCampaign(campaign.keitaro_id, true));
  head.append(title, fetchButton);

  const flows = document.createElement("div");
  flows.className = "flows";
  const label = document.createElement("p");
  label.className = "flows-label";
  label.textContent = "Потоки";
  flows.appendChild(label);
  for (const stream of data.streams) {
    flows.appendChild(renderStream(campaign.keitaro_id, stream));
  }

  board.append(head, flows);
  editor.appendChild(board);
}

function renderStream(campaignId, stream) {
  const card = document.createElement("article");
  card.className = "stream" + (stream.dirty ? " dirty" : "");
  const head = document.createElement("div");
  head.className = "stream-head";
  const title = document.createElement("div");
  const state = stream.dirty ? "черновик" : "синхронизировано";
  title.innerHTML = `<h3>${escapeHtml(stream.name)}</h3><span class="status">${escapeHtml(stream.stream_type)} · ${state}</span>`;
  head.appendChild(title);
  if (stream.accepts_offers) {
    const actions = document.createElement("div");
    actions.className = "stream-actions";
    actions.append(
      actionButton("Push", () => mutate(`/api/campaigns/${campaignId}/streams/${stream.id}/push`)),
      actionButton("Cancel", () => mutate(`/api/campaigns/${campaignId}/streams/${stream.id}/cancel`)),
    );
    head.appendChild(actions);
  }
  card.appendChild(head);

  if (!stream.accepts_offers) {
    const note = document.createElement("p");
    note.className = "quiet";
    note.textContent = "Без офферов";
    card.appendChild(note);
    return card;
  }

  const offers = document.createElement("div");
  offers.className = "offers";
  for (const offer of stream.offers) {
    offers.appendChild(renderOffer(campaignId, stream.id, offer));
  }
  card.appendChild(offers);

  const add = document.createElement("div");
  add.className = "add-line";
  const picker = document.createElement("div");
  picker.className = "picker";
  const input = document.createElement("input");
  input.placeholder = "найти оффер и добавить";
  const results = document.createElement("div");
  results.className = "results";
  picker.append(input, results);
  let picked = null;
  bindSearch(input, results, (row) => { picked = row; });
  const button = actionButton("Добавить", async () => {
    if (!picked) throw new Error("Выбери оффер из подсказки");
    await mutate(`/api/campaigns/${campaignId}/streams/${stream.id}/offers`, { offer_id: picked.id });
  });
  add.append(picker, button);
  card.appendChild(add);
  return card;
}

function renderOffer(campaignId, streamId, offer) {
  const row = document.createElement("div");
  row.className = "offer" + (offer.status === "removed" ? " removed" : "");
  const info = document.createElement("div");
  info.innerHTML = `<span class="name">[${offer.offer_id}] ${escapeHtml(offer.name)}</span>`;
  const controls = document.createElement("div");
  controls.className = "controls";
  const share = document.createElement("span");
  share.className = "share";
  share.textContent = `${offer.share}%`;
  controls.appendChild(share);
  if (offer.status === "active") {
    const pin = document.createElement("label");
    pin.className = "pin";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = offer.pinned;
    checkbox.addEventListener("change", () => {
      mutate(`/api/campaigns/${campaignId}/streams/${streamId}/offers/${offer.id}/pin`, { pinned: checkbox.checked })
        .catch((error) => { checkbox.checked = offer.pinned; showError(error); });
    });
    pin.append(checkbox, document.createTextNode("pin"));
    const remove = actionButton("Remove", () => mutate(`/api/campaigns/${campaignId}/streams/${streamId}/offers/${offer.id}/remove`));
    controls.append(pin, remove);
  } else {
    controls.append(actionButton("Bring back", () => mutate(`/api/campaigns/${campaignId}/streams/${streamId}/offers/${offer.id}/restore`)));
  }
  row.append(info, controls);
  return row;
}

function actionButton(label, task) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  if (label === "Push" || label === "Добавить") button.className = "primary";
  if (label === "Cancel" || label === "Bring back") button.className = "ghost";
  if (label === "Remove") button.className = "danger";
  button.addEventListener("click", () => run(task));
  return button;
}

async function mutate(path, body) {
  clearError();
  const data = await api(path, { method: "POST", body: JSON.stringify(body || {}) });
  renderEditor(data);
}

async function run(task) {
  if (busy) return;
  busy = true;
  document.querySelectorAll("button").forEach((button) => { button.disabled = true; });
  try {
    await task();
  } catch (error) {
    showError(error);
  } finally {
    busy = false;
    document.querySelectorAll("button").forEach((button) => { button.disabled = false; });
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
}

loadMeta();
loadCampaigns().catch(showError);
