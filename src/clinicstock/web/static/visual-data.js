function drawProjectChart(target, points) {
    const histogram = named('div',undefined,'demand-histogram');
    const maximum = Math.max(1, ...points.map(row=>Math.abs(row.value)));
    for (const point of points.slice(0,9)) {
        const pillar = named('div',undefined,'demand-pillar');
        const fill = named('span',undefined,'demand-volume');
        fill.style.height = `${Math.max(2,Math.abs(point.value) / maximum * 96)}px`;
        pillar.append(named('b',point.value),fill,named('small',point.label));
        histogram.append(pillar);
    }
    target.append(histogram);
}
