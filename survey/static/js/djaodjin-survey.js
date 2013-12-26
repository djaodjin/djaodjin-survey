/** Draws a pie chart of *data* inside the HTML *container* node.
 */
function updateChart(container, data) {
	var col = 0;
	nv.addGraph(function() {
		var chart = nv.models.pieChart()
			.x(function(d) { return d.label + ' ('+ d.value + ')' })
			.y(function(d) { return d.value })
			.showLabels(true)
			.labelThreshold(.05)
			.labelType("percent")
			.donut(true)
			.donutRatio(0.35)
			.color(d3.scale.category10().range());

		d3.select(container)
			.datum(data)
			.transition().duration(1200)
		.call(chart);

		return chart;
	});
}
