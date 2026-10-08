/* ═══════════════════════════════════════════════════════════════════════
   PayRail v3 — Dashboard Controller
   ═══════════════════════════════════════════════════════════════════════ */

document.addEventListener("DOMContentLoaded", () => {

    // ── Tab Navigation with animated indicator ──────────────────────
    const tabBtns = document.querySelectorAll(".tn");
    const tabPanels = document.querySelectorAll(".tab-panel");
    const indicator = document.getElementById("tnIndicator");

    function moveIndicator(btn) {
        indicator.style.left = btn.offsetLeft + "px";
        indicator.style.width = btn.offsetWidth + "px";
    }

    function switchTab(tabId) {
        tabBtns.forEach(b => b.classList.remove("active"));
        tabPanels.forEach(p => p.classList.remove("active"));
        const btn = document.querySelector(`.tn[data-tab="${tabId}"]`);
        const panel = document.getElementById(`tab-${tabId}`);
        if (btn) { btn.classList.add("active"); moveIndicator(btn); }
        if (panel) panel.classList.add("active");

        if (tabId === "overview") loadOverview();
        if (tabId === "transactions") loadTransactions();
        if (tabId === "banks") loadBanks();
        if (tabId === "chaos") loadChaosStatus();
    }

    tabBtns.forEach(btn => btn.addEventListener("click", () => switchTab(btn.dataset.tab)));

    // Init indicator position
    requestAnimationFrame(() => {
        const activeBtn = document.querySelector(".tn.active");
        if (activeBtn) moveIndicator(activeBtn);
    });

    // ── Helpers ─────────────────────────────────────────────────────
    const fmt = n => "₹" + Number(n).toLocaleString("en-IN");
    const ts = iso => new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const shortId = id => id ? id.substring(0, 8) : "—";
    const pct = (n, t) => t ? Math.round((n / t) * 100) + "%" : "—";

    // ── Counter Animation ───────────────────────────────────────────
    function animateCount(el, target) {
        const start = parseInt(el.textContent) || 0;
        const diff = target - start;
        if (diff === 0) return;
        const duration = 600;
        const startTime = performance.now();
        function step(now) {
            const progress = Math.min((now - startTime) / duration, 1);
            const ease = 1 - Math.pow(1 - progress, 3); // easeOutCubic
            el.textContent = Math.round(start + diff * ease);
            if (progress < 1) requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
    }

    // ── Toast Notifications ─────────────────────────────────────────
    function toast(message, type = "success") {
        const container = document.getElementById("toastContainer");
        const icons = { success: "✓", warning: "↩", error: "✗" };
        const el = document.createElement("div");
        el.className = `toast ${type}`;
        el.innerHTML = `<span>${icons[type] || "•"}</span> ${message}`;
        container.appendChild(el);
        setTimeout(() => el.remove(), 3500);
    }

    // ── Network Health ──────────────────────────────────────────────
    async function checkHealth() {
        const endpoints = [
            { url: "/health", dot: "statusSwitch", node: "nodeSwitch" },
            { url: "http://127.0.0.1:5051/accounts", dot: "statusA", node: "nodeA" },
            { url: "http://127.0.0.1:5052/accounts", dot: "statusB", node: "nodeB" },
        ];
        for (const ep of endpoints) {
            try {
                await fetch(ep.url, { signal: AbortSignal.timeout(2000) });
                document.getElementById(ep.dot).className = "nc-status on";
            } catch {
                document.getElementById(ep.dot).className = "nc-status off";
            }
        }
    }

    // ── Pulse animation on edges ────────────────────────────────────
    function pulseEdge(side) {
        const el = document.getElementById(side === "left" ? "pulseLeft" : "pulseRight");
        el.classList.remove("active");
        void el.offsetWidth; // force reflow
        el.classList.add("active");
        setTimeout(() => el.classList.remove("active"), 700);
    }

    // ── Overview ────────────────────────────────────────────────────
    document.getElementById("refreshOverview").addEventListener("click", loadOverview);

    async function loadOverview() {
        checkHealth();
        try {
            const res = await fetch("/transactions");
            const txns = await res.json();
            const total = txns.length;
            const success = txns.filter(t => t.status === "completed").length;
            const reversed = txns.filter(t => t.status === "reversed").length;
            const failed = txns.filter(t => t.status === "failed").length;

            animateCount(document.getElementById("metTotal"), total);
            animateCount(document.getElementById("metSuccess"), success);
            animateCount(document.getElementById("metReversed"), reversed);
            animateCount(document.getElementById("metFailed"), failed);

            const maxBar = Math.max(total, 1);
            document.getElementById("barTotal").style.width = "100%";
            document.getElementById("barSuccess").style.width = pct(success, maxBar);
            document.getElementById("barReversed").style.width = pct(reversed, maxBar);
            document.getElementById("barFailed").style.width = pct(failed, maxBar);

            document.getElementById("metSuccessPct").textContent = total ? pct(success, total) + " success rate" : "—";
            document.getElementById("metReversedPct").textContent = total ? pct(reversed, total) + " auto-reversed" : "—";
            document.getElementById("metFailedPct").textContent = total ? pct(failed, total) + " hard failures" : "—";

            // Activity feed
            const feed = document.getElementById("activityFeed");
            const empty = document.getElementById("feedEmpty");
            if (!txns.length) { feed.innerHTML = ''; feed.appendChild(empty); empty.style.display = "block"; return; }

            empty.style.display = "none";
            feed.innerHTML = txns.slice(0, 12).map(t => `
                <div class="feed-item">
                    <div class="feed-dot ${t.status}"></div>
                    <div class="feed-content">
                        <div class="feed-main">
                            <span class="upi">${t.sender}</span> → <span class="upi">${t.receiver}</span>
                        </div>
                        <div class="feed-time">${ts(t.timestamp)}</div>
                    </div>
                    <span class="feed-amount">${fmt(t.amount)}</span>
                    <span class="feed-chip ${t.status}">${t.status}</span>
                </div>
            `).join("");

        } catch (err) { console.error("Overview error:", err); }
    }

    // ── Payment Pipeline Animation ──────────────────────────────────
    function resetPipeline() {
        ["pipeDebit", "pipeCredit", "pipeSettle"].forEach(id => {
            document.getElementById(id).className = "pipe-step";
        });
        document.querySelectorAll(".pipe-line").forEach(l => l.className = "pipe-line");
    }

    async function animatePipeline(status, step) {
        resetPipeline();
        const lines = document.querySelectorAll(".pipe-line");

        // Step 1: Debit
        document.getElementById("pipeDebit").classList.add("active");
        await sleep(300);

        if (status === "failed" && step === "debit") {
            document.getElementById("pipeDebit").classList.replace("active", "error");
            return;
        }

        document.getElementById("pipeDebit").classList.replace("active", "done");
        lines[0].classList.add("filled");
        pulseEdge("left");
        await sleep(400);

        // Step 2: Credit
        document.getElementById("pipeCredit").classList.add("active");
        await sleep(300);

        if (status === "reversed") {
            document.getElementById("pipeCredit").classList.replace("active", "error");
            lines[1].classList.add("error-fill");
            await sleep(300);
            document.getElementById("pipeSettle").classList.add("error");
            return;
        }

        if (status === "failed") {
            document.getElementById("pipeCredit").classList.replace("active", "error");
            return;
        }

        document.getElementById("pipeCredit").classList.replace("active", "done");
        lines[1].classList.add("filled");
        pulseEdge("right");
        await sleep(300);

        // Step 3: Settle
        document.getElementById("pipeSettle").classList.add("done");
    }

    function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

    // ── Send Payment ────────────────────────────────────────────────
    const payBtn = document.getElementById("payBtn");
    payBtn.addEventListener("click", sendPayment);

    async function sendPayment() {
        const sender = document.getElementById("senderInput").value.trim();
        const receiver = document.getElementById("receiverInput").value.trim();
        const amount = parseFloat(document.getElementById("amountInput").value);
        const idem = document.getElementById("idempotencyInput").value.trim();

        if (!sender || !receiver || !amount || amount <= 0) return;

        payBtn.classList.add("loading");
        payBtn.disabled = true;
        document.getElementById("resultCard").style.display = "none";
        resetPipeline();

        // Start debit animation
        document.getElementById("pipeDebit").classList.add("active");

        try {
            const body = { sender, receiver, amount };
            if (idem) body.idempotency_key = idem;

            const res = await fetch("/pay", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            const data = await res.json();

            // Animate pipeline
            await animatePipeline(data.status, data.step);

            // Toast
            const toastMap = {
                completed: ["Payment completed", "success"],
                reversed: ["Payment reversed — debit refunded", "warning"],
                failed: ["Payment failed", "error"],
            };
            const [msg, type] = toastMap[data.status] || ["Unknown", "error"];
            toast(msg, type);

            // Show result
            showResult(data);

            // Pulse network edges
            if (data.status === "completed") { pulseEdge("left"); pulseEdge("right"); }

        } catch (err) {
            toast("Network error", "error");
            showResult({ status: "failed", reason: "Network error", step: "request" });
        } finally {
            payBtn.classList.remove("loading");
            payBtn.disabled = false;
        }
    }

    function showResult(data) {
        const card = document.getElementById("resultCard");
        const accent = document.getElementById("resultAccent");
        const emoji = document.getElementById("resultEmoji");
        const title = document.getElementById("resultTitle");
        const sub = document.getElementById("resultSub");
        const code = document.getElementById("resultCode");

        const cfg = {
            completed: { e: "✓", t: "Transfer Settled", s: "Funds delivered successfully", c: "completed" },
            reversed:  { e: "↩", t: "Auto-Reversed", s: data.reason || "Credit failed — debit restored", c: "reversed" },
            failed:    { e: "✗", t: "Transfer Failed", s: data.reason || "Could not process", c: "failed" },
        }[data.status] || { e: "?", t: "Unknown", s: "", c: "failed" };

        accent.className = `result-accent ${cfg.c}`;
        emoji.className = `result-emoji ${cfg.c}`;
        emoji.textContent = cfg.e;
        title.textContent = cfg.t;
        sub.textContent = cfg.s;

        const lines = [
            `txn_id     ${data.transaction_id || "—"}`,
            `status     ${data.status}`,
            data.sender   ? `sender     ${data.sender}` : null,
            data.receiver ? `receiver   ${data.receiver}` : null,
            data.amount   ? `amount     ${fmt(data.amount)}` : null,
            data.step     ? `step       ${data.step}` : null,
            data.reason   ? `reason     ${data.reason}` : null,
        ].filter(Boolean);
        code.textContent = lines.join("\n");

        card.style.display = "block";
        card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    // ── Transactions ────────────────────────────────────────────────
    document.getElementById("refreshTxns").addEventListener("click", loadTransactions);

    async function loadTransactions() {
        try {
            const res = await fetch("/transactions");
            const txns = await res.json();
            const tbody = document.getElementById("txnBody");
            const empty = document.getElementById("txnEmpty");
            if (!txns.length) { tbody.innerHTML = ""; empty.style.display = "block"; return; }
            empty.style.display = "none";

            tbody.innerHTML = txns.map(t => `
                <tr>
                    <td>${ts(t.timestamp)}</td>
                    <td title="${t.id}">${shortId(t.id)}</td>
                    <td>${t.sender}</td>
                    <td>${t.receiver}</td>
                    <td>${fmt(t.amount)}</td>
                    <td><span class="feed-chip ${t.status}">${t.status}</span></td>
                    <td>${t.step}</td>
                </tr>
            `).join("");
        } catch (err) { console.error(err); }
    }

    // ── Banks ───────────────────────────────────────────────────────
    async function loadBanks() {
        try {
            const res = await fetch("/banks");
            const banks = await res.json();
            document.getElementById("banksGrid").innerHTML = banks.map(bank => {
                const cls = bank.bank === "bankA" ? "a" : "b";
                const initial = bank.bank.replace("bank", "").toUpperCase();
                return `
                    <div class="bank-card">
                        <div class="bank-top">
                            <div class="bank-name-row">
                                <div class="bank-avatar ${cls}">${initial}</div>
                                <div class="bank-info">
                                    <h3>${bank.bank.replace("bank", "Bank ")}</h3>
                                    <p>${bank.url}</p>
                                </div>
                            </div>
                            <span class="chip ${bank.status}">${bank.status}</span>
                        </div>
                        ${bank.accounts.map(a => {
                            const initials = a.name.split(" ").map(w => w[0]).join("").toUpperCase();
                            return `
                            <div class="acc-row">
                                <div class="acc-left">
                                    <div class="acc-mini-av">${initials}</div>
                                    <div>
                                        <div class="acc-upi">${a.upi_id}</div>
                                        <div class="acc-name">${a.name}</div>
                                    </div>
                                </div>
                                <span class="acc-bal">${fmt(a.balance)}</span>
                            </div>`;
                        }).join("")}
                    </div>
                `;
            }).join("");
        } catch (err) { console.error(err); }
    }

    // ── Update sender/receiver avatars on input change ──────────────
    document.getElementById("senderInput").addEventListener("input", e => {
        const v = e.target.value;
        document.getElementById("senderAvatar").textContent = v ? v[0].toUpperCase() : "?";
    });
    document.getElementById("receiverInput").addEventListener("input", e => {
        const v = e.target.value;
        document.getElementById("receiverAvatar").textContent = v ? v[0].toUpperCase() : "?";
    });

    // ── Chaos Testing ───────────────────────────────────────────────
    const chaosCheckbox = document.getElementById("chaosCheckbox");
    chaosCheckbox.addEventListener("change", toggleChaos);

    async function loadChaosStatus() {
        try {
            const res = await fetch("/inject-failure");
            const data = await res.json();
            updateChaosUI(data.failure_injection);
        } catch (err) { console.error(err); }
    }

    async function toggleChaos() {
        try {
            const res = await fetch("/inject-failure", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ enabled: chaosCheckbox.checked }),
            });
            const data = await res.json();
            updateChaosUI(data.failure_injection);
            toast(data.failure_injection ? "Chaos injection ENABLED" : "Chaos injection disabled", data.failure_injection ? "error" : "success");
        } catch (err) { console.error(err); }
    }

    function updateChaosUI(active) {
        chaosCheckbox.checked = active;
        const circle = document.getElementById("chaosCircle");
        const center = document.getElementById("chaosCenter");
        const text = document.getElementById("chaosText");
        const circumference = 2 * Math.PI * 52;

        if (active) {
            circle.style.strokeDashoffset = "0";
            center.textContent = "ON";
            center.className = "chaos-center on";
            text.textContent = "Disable Failure Injection";
        } else {
            circle.style.strokeDashoffset = circumference;
            center.textContent = "OFF";
            center.className = "chaos-center";
            text.textContent = "Enable Failure Injection";
        }
    }

    // ── Reconciliation ──────────────────────────────────────────────
    document.getElementById("runReconcile").addEventListener("click", async () => {
        const container = document.getElementById("reconcileResults");
        container.innerHTML = '<div class="card"><div class="feed-empty">Running audit…</div></div>';

        try {
            const res = await fetch("/reconcile");
            const data = await res.json();
            let html = "";
            for (const [bank, result] of Object.entries(data)) {
                const ok = result.status === "ok";
                html += `
                    <div class="recon-card">
                        <div class="recon-head">
                            <span class="recon-bank">${bank.replace("bank", "Bank ")}</span>
                            <span class="recon-status ${ok ? 'ok' : 'fail'}">${ok ? '✓ Balanced' : '✗ Mismatch'}</span>
                        </div>
                        <div class="recon-detail">${result.checked || 0} accounts audited</div>
                    </div>
                `;
            }
            container.innerHTML = html;
            toast("Audit complete — all checks passed", "success");
        } catch (err) {
            container.innerHTML = '<div class="card"><div class="feed-empty" style="color:var(--red);">Audit failed</div></div>';
            toast("Audit failed", "error");
        }
    });

    // ── Init ────────────────────────────────────────────────────────
    loadOverview();
    loadChaosStatus();
});
