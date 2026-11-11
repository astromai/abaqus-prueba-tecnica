"use strict";

const dashboard = document.querySelector("#dashboard");
const dateForm = document.querySelector("#date-form");
const byId = (id) => document.getElementById(id);
const svgNS = "http://www.w3.org/2000/svg";
const portfolioColors = ["#116c5d", "#965315"];
const assetColors = [
    "#245f83", "#de9f25", "#217e72", "#9d537c", "#a5493d", "#6d63ae",
    "#4b782d", "#bf6740", "#52a7a0", "#65738b", "#cf806a", "#739dca",
    "#88722f", "#444f75", "#8eae5a", "#b981ad", "#755546",
];
const money = new Intl.NumberFormat("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 });
const quantity = new Intl.NumberFormat("es-CL", { maximumFractionDigits: 8 });
const percent = new Intl.NumberFormat("es-CL", { style: "percent", maximumFractionDigits: 2 });
const shortDate = new Intl.DateTimeFormat("es-CL", { day: "2-digit", month: "2-digit", year: "2-digit", timeZone: "UTC" });

function element(tag, text) {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
}

function svgElement(tag, attributes, parent, text) {
    const node = document.createElementNS(svgNS, tag);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
    if (text !== undefined) node.textContent = text;
    parent.append(node);
    return node;
}

function setStatus(id, message, error = false) {
    const status = byId(id);
    status.textContent = message;
    status.dataset.error = error;
}

async function getJson(url, signal) {
    const response = await fetch(url, { signal, headers: { Accept: "application/json" } });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "La API no pudo completar la consulta.");
    return data;
}

function renderLegend(container, labels, colors) {
    container.replaceChildren();
    labels.forEach((label, index) => {
        const item = element("li", "");
        const swatch = element("span", "");
        swatch.className = "swatch";
        swatch.style.backgroundColor = colors[index % colors.length];
        swatch.setAttribute("aria-hidden", "true");
        item.append(swatch, document.createTextNode(label));
        container.append(item);
    });
}

function chartAxes(container, dates, ticks, tickLabel, title, height) {
    const width = Math.max(270, Math.floor(container.clientWidth));
    const left = 49;
    const right = width - 26;
    const top = 15;
    const bottom = height - 32;
    const start = dates[0];
    const end = dates.at(-1);
    const x = (time) => end === start ? (left + right) / 2 : left + (right - left) * (time - start) / (end - start);
    const low = ticks[0];
    const high = ticks.at(-1);
    const y = (value) => bottom - (bottom - top) * (value - low) / (high - low);
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", [0, 0, width, height].join(" "));
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", title);
    container.replaceChildren(svg);
    for (const tick of ticks) {
        svgElement("line", { x1: left, x2: right, y1: y(tick), y2: y(tick), stroke: "#dce7e6" }, svg);
        svgElement("text", { x: left - 8, y: y(tick) + 4, "text-anchor": "end" }, svg, tickLabel(tick));
    }
    const labelCount = Math.min(dates.length, width < 460 ? 3 : 5);
    for (let i = 0; i < labelCount; i += 1) {
        const index = labelCount === 1 ? 0 : Math.round(i * (dates.length - 1) / (labelCount - 1));
        const day = dates[index];
        svgElement("text", { x: x(day), y: bottom + 23, "text-anchor": "middle" }, svg, shortDate.format(day));
    }
    return { svg, x, y, left, right };
}

function renderValueChart(portfolios, dates) {
    const values = portfolios.map((portfolio) => portfolio.serie.map((point) => Number(point.valor_total) / 1e6));
    const allValues = values.flat();
    const minimum = Math.min(...allValues);
    const maximum = Math.max(...allValues);
    const step = Math.max(5, Math.ceil((maximum - minimum) / 20) * 5);
    const low = Math.floor(minimum / step) * step;
    const high = Math.max(low + 2 * step, Math.ceil(maximum / step) * step);
    const ticks = Array.from({ length: (high - low) / step + 1 }, (_, index) => low + step * index);
    const { svg, x, y } = chartAxes(byId("value-chart"), dates, ticks, (tick) => String(tick),
        "Gráfico de líneas del valor total de ambos portafolios en millones de pesos", 272);

    values.forEach((series, index) => {
        const color = portfolioColors[index % portfolioColors.length];
        const points = series.map((value, i) => [x(Date.parse(portfolios[index].serie[i].fecha)), y(value)].join(","));
        if (series.length === 1) {
            const [cx, cy] = points[0].split(",");
            svgElement("circle", { cx, cy, r: 4 + 2 * (values.length - index - 1), fill: color }, svg);
        } else {
            svgElement("polyline", {
                points: points.join(" "),
                fill: "none",
                stroke: color,
                "stroke-width": 2.5,
                "stroke-linejoin": "round",
                "stroke-dasharray": index === 1 ? "5 3" : "none",
            }, svg);
        }
    });
}

function renderWeightChart(container, portfolio, assets, dates) {
    const { svg, x, y, left, right } = chartAxes(container, dates, [0, .25, .5, .75, 1], percent.format,
        "Áreas apiladas de composición del portafolio " + portfolio.id, 226);
    const pointDates = portfolio.serie.map((point) => Date.parse(point.fecha));
    const base = pointDates.map(() => 0);

    assets.forEach((asset, index) => {
        const bottom = base.map((value, i) => [x(pointDates[i]), y(value)]);
        const top = base.map((value, i) => {
            base[i] = Math.min(1, value + Number(portfolio.serie[i].pesos[asset] || 0));
            return [x(pointDates[i]), y(base[i])];
        });
        if (top.every((point, i) => point[1] === bottom[i][1])) return;
        const points = top.length === 1 && dates.length === 1
            ? [[left, top[0][1]], [right, top[0][1]], [right, bottom[0][1]], [left, bottom[0][1]]]
            : [...top, ...bottom.reverse()];
        if (top.length === 1 && dates.length > 1) {
            const [cx, cy] = top[0];
            points.splice(0, points.length, [cx - 3, cy], [cx + 3, cy], [cx + 3, bottom[0][1]], [cx - 3, bottom[0][1]]);
        }
        const area = svgElement("polygon", {
            points: points.map((point) => point.join(",")).join(" "),
            fill: assetColors[index % assetColors.length],
        }, svg);
        svgElement("title", {}, area, asset);
    });
}

function renderEvolution(portfolios) {
    const series = portfolios.filter((portfolio) => portfolio.serie.length);
    const dates = [...new Set(series.flatMap((portfolio) => portfolio.serie.map((point) => Date.parse(point.fecha))))].sort((a, b) => a - b);
    const assets = [...new Set(series.flatMap((portfolio) => Object.keys(portfolio.serie[0].pesos)))];
    byId("results").hidden = !dates.length;
    if (!dates.length) {
        setStatus("chart-status", "No hay observaciones en el período solicitado.");
        return;
    }
    setStatus("chart-status", dates.length + (dates.length === 1 ? " fecha observada." : " fechas observadas."));
    renderLegend(byId("value-legend"), series.map((portfolio) => "Portafolio " + portfolio.id), portfolioColors);
    renderLegend(byId("weight-legend"), assets, assetColors);
    renderValueChart(series, dates);

    const weights = byId("weight-charts");
    weights.replaceChildren();
    const summary = byId("summary");
    summary.replaceChildren();
    for (const portfolio of series) {
        const section = element("div", "");
        const frame = element("div", "");
        frame.className = "chart-frame";
        section.append(element("h3", "Portafolio " + portfolio.id), frame);
        weights.append(section);
        renderWeightChart(frame, portfolio, assets, dates);

        const first = Number(portfolio.serie[0].valor_total);
        const latest = portfolio.serie.at(-1);
        const last = Number(latest.valor_total);
        const line = element("p", "Portafolio " + portfolio.id + " al " + shortDate.format(Date.parse(latest.fecha)) + " · ");
        line.append(element("strong", money.format(last)), document.createTextNode(" (" + percent.format(last / first - 1) + " en el período)"));
        summary.append(line);
    }
}

function renderPositions(portfolios) {
    const container = byId("positions");
    container.replaceChildren();
    for (const portfolio of portfolios) {
        const section = element("div", "");
        const heading = "Portafolio " + portfolio.id;
        section.append(element("h3", heading));
        section.append(element("p", shortDate.format(Date.parse(portfolio.fecha_inicial)) + " · " + money.format(Number(portfolio.valor_inicial))));
        const table = element("table", "");
        table.setAttribute("aria-label", "Posiciones iniciales del " + heading);
        const header = table.createTHead().insertRow();
        for (const name of ["Activo", "Peso", "Cantidad", "Monto ($)"]) {
            const cell = element("th", name);
            cell.scope = "col";
            header.append(cell);
        }
        const body = table.createTBody();
        for (const position of portfolio.posiciones) {
            const row = body.insertRow();
            const label = element("th", position.activo);
            label.scope = "row";
            row.append(label);
            row.insertCell().textContent = percent.format(Number(position.peso_inicial));
            row.insertCell().textContent = quantity.format(Number(position.cantidad));
            row.insertCell().textContent = money.format(Number(position.monto_inicial));
        }
        const scroll = element("div", "");
        scroll.className = "table-wrap";
        scroll.append(table);
        section.append(scroll);
        container.append(section);
    }
}

let activeRequest;
let displayedPortfolios;

async function loadEvolution() {
    activeRequest?.abort();
    const controller = new AbortController();
    activeRequest = controller;
    displayedPortfolios = undefined;
    byId("results").hidden = true;
    setStatus("chart-status", "Consultando la API…");
    try {
        const params = new URLSearchParams(new FormData(dateForm));
        const data = await getJson(dashboard.dataset.evolutionUrl + "?" + params, controller.signal);
        if (controller.signal.aborted) return;
        displayedPortfolios = data.portafolios;
        renderEvolution(displayedPortfolios);
    } catch (error) {
        if (!controller.signal.aborted) {
            byId("results").hidden = true;
            setStatus("chart-status", "No se pudo cargar la evolución. " + error.message, true);
        }
    }
}

if (dateForm) {
    dateForm.addEventListener("submit", (event) => {
        event.preventDefault();
        loadEvolution();
    });
    let resizeFrame;
    window.addEventListener("resize", () => {
        cancelAnimationFrame(resizeFrame);
        resizeFrame = requestAnimationFrame(() => {
            if (displayedPortfolios) renderEvolution(displayedPortfolios);
        });
    });
    loadEvolution();
}

setStatus("positions-status", "Consultando las posiciones iniciales…");
getJson(dashboard.dataset.positionsUrl).then(({ portafolios }) => {
    renderPositions(portafolios);
    setStatus("positions-status", portafolios.length ? "" : "Todavía no hay posiciones cargadas.");
}).catch((error) => setStatus("positions-status", "No se pudieron cargar las posiciones. " + error.message, true));
