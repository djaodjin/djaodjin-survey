(function ($) {
    "use strict";

    var DjSet = DjaoDjinSet.DjSet;

    /** Matrix Chart
        <div id="#_chart_">
          <div class="chart">
          </div>
          <input type="text" name="title">
          <input class="cohort" type="checkbox" name="cohorts">
          <input class="metric" type="radio" name="metric">
        </div>
     */
    function DJMatrixChart(el, options){
        this.element = el;
        this.$element = $(el);
        this.options = options;

        this.samples = [];
        this.cohorts = [];
        this.accounts = [];
        this.questions = [];
        this.metrics = [];
        this.aggregates = [];

        this.selectedMetric = null;
        this.selectedCohorts = [];

        this.init();
    }

    DJMatrixChart.prototype = {

        _csrfToken: function() {
            var self = this;
            if( self.options.csrfToken ) { return self.options.csrfToken; }
            return getMetaCSRFToken();
        },

        init: function () {
            var self = this;

            self.$selectionElement = self.$element;
            if( self.options.selection_element ) {
                self.$selectionElement = $(self.options.selection_element);
            }

            self.$selectionElement.find("[name='title']").on('input', function() {
                self._save();
            });
            self.$selectionElement.find("[name=\"metric\"]").change(function() {
                self._save();
                self.updateChart();
            });
            self.$selectionElement.find("[name=\"cohorts\"]").change(function() {
                self._save();
                self.updateChart();
            });
            self._updateSelectionFromUI();
            if( self.options.data ) {
                self._update(self.options.data);
            } else {
                self._load();
            }
        },

        /** Update the selected metric and cohorts from the UI elements.
         */
        _updateSelectionFromUI: function() {
            var self = this;

            var metricElements = self.$selectionElement.find("[name=\"metric\"]:checked");
            if( metricElements.length > 0 ) {
                var $element = $(metricElements[0]);
                var elementVal = $element.val();
                self.selectedMetric = {slug: elementVal};
            }

            var cohortElements = self.$selectionElement.find("[name=\"cohorts\"]");
            for( var cohortIdx = 0; cohortIdx < cohortElements.length; ++cohortIdx ) {
                var $element = $(cohortElements[cohortIdx]);
                var elementVal = $element.val();
                if( $element.is(":checked") ) {
                    var found = -1;
                    for ( var idx = 0 ; idx < self.selectedCohorts.length; ++idx ){
                        if( self.selectedCohorts[idx].slug === elementVal ) {
                            found = idx;
                        }
                    }
                    if( found < 0 ) {
                        var title = $element.parent().text().replace(
                                /^\s+|\s+$/g,''); // label
                        self.selectedCohorts.push(
                            {slug: elementVal, title: title});
                    }
                } else {
                    var found = -1;
                    for ( var idx = 0 ; idx < self.selectedCohorts.length; ++idx ){
                        if( self.selectedCohorts[idx].slug === elementVal ) {
                            found = idx;
                        }
                    }
                    if( found >= 0 ) {
                        self.selectedCohorts.splice(found, 1);
                    }
                }
            }
        },

        /** *data* is an array whose 1st component will be used for bars
            and (optional) second component used for horizontal lines.
         */
        _update: function(data) {
            var self = this;
            var bData = data[0];
            self.scores = bData.values;
            for( var idx = 0; idx < bData.cohorts.length; ++idx ) {
                if( !bData.cohorts[idx].hasOwnProperty('title') ) {
                    if( bData.cohorts[idx].hasOwnProperty('printable_name') ) {
                        bData.cohorts[idx].title =
                            data.cohorts[idx].printable_name;
                    } else {
                        bData.cohorts[idx].title = "cohort-" + idx;
                    }
                }
            }
            self.selectedCohorts = bData.cohorts;
            self.selectedMetric = bData.metric;
            if( data.length > 1 ) {
                self.aggregates = data[1].cohorts;
                self.aggregateScores = data[1].values;
            }
            self.updateChart();
        },

        _load: function() {
            var self = this;
            var data = {}
            for( var idx = 0; idx < self.selectedCohorts.length; ++idx ) {
                var cohort = self.selectedCohorts[idx];
                data[cohort.slug] = 1;
            }
            $.ajax({
                method: "GET",
                url: self.options.matrix_api,
                data: data,
                contentType: "application/json; charset=utf-8",
                success: function(data) {
                    self._update(data);
                    self.$element.trigger("matrix.loaded");
                },
                error: function(resp) {
                    if( resp.status === 404 ) {
                        var svgContainer = self.$element.find(".chart")[0];
                        $(svgContainer).empty();
                        $(svgContainer).append('<div>Not found</div>');
                    }
                }
            });
        },

        _save: function() {
            var self = this;
            self._updateSelectionFromUI();
            var data = {
                title: self.$selectionElement.find("[name=\"title\"]").val(),
                cohorts: self.selectedCohorts
            };
            if( self.selectedMetric ) {
                data['metric'] = self.selectedMetric;
                if( !data['metric'].hasOwnProperty('title') ) {
                    data['metric']['title'] = "blank";
                }
                if( !data['metric'].hasOwnProperty('tags') ) {
                    data['metric']['tags'] = "blank";
                }
                if( !data['metric'].hasOwnProperty('predicates') ) {
                    data['metric']['predicates'] = [];
                }
            }
            for( var idx = 0; idx < data['cohorts'].length; ++idx ) {
                var cohort = data['cohorts'][idx];
                if( !data['cohorts'][idx].hasOwnProperty('title')
                  || data['cohorts'][idx].title === "" ) {
                    if( data['cohorts'][idx].hasOwnProperty('printable_name')
                        && data['cohorts'][idx].printable_name !== "" ) {
                        data['cohorts'][idx]['title']
                            = data['cohorts'][idx].printable_name;
                    } else {
                        data['cohorts'][idx]['title'] = "cohort-" + idx;
                    }
                }
                if( !data['cohorts'][idx].hasOwnProperty('tags')
                    || data['cohorts'][idx].tags === "" ) {
                    data['cohorts'][idx]['tags'] = "blank";
                }
                if( !data['cohorts'][idx].hasOwnProperty('predicates') ) {
                    data['cohorts'][idx]['predicates'] = [];
                }
            }
            $.ajax({
                method: "PUT",
                url: self.options.matrix_api,
                data: JSON.stringify(data),
                datatype: "json",
                contentType: "application/json; charset=utf-8",
                success: function(data) {
                },
                error: function(resp) {
                }
            });
        },

        /** This function will recompute the scores by applying the filters
            on a Sample set on the client in Javascript.

            (Currently not used)
         */
        scoresFromSet: function() {
            var self = this;

            $.ajax({
                method: "GET",
                url: self.options.editable_filter_api + "?q=cohort",
                datatype: "json",
                contentType: "application/json; charset=utf-8",
                success: function(data) {
                    self.cohorts = data.results;
                    var $cohorts = self.$selectionElement.find("[name=\"cohorts\"]");
                    $cohorts.empty();
                    for ( var i = 0; i < self.cohorts.length; i ++){
                        var $option = $('<option/>');
                        var cohort = self.cohorts[i];
                        $option.attr('value', cohort.slug);
                        $option.text(cohort.title);
                        $cohorts.append($option);
                    }
                    self._scoresFromSet();
                }
            });

            $.ajax({
                method: "GET",
                url: self.options.editable_filter_api + "?q=metric",
                datatype: "json",
                contentType: "application/json; charset=utf-8",
                success: function(data) {
                    self.metrics = data.results;
                    var $metrics = self.$selectionElement.find("[name=\"metric\"]");
                    $metrics.empty();
                    for ( var i = 0; i < self.metrics.length; i ++){
                        var $option = $('<option/>');
                        var qc = self.metrics[i];
                        $option.text(qc.title);
                        $option.attr('value', qc.slug);
                        $metrics.append($option);
                    }
                    self._scoresFromSet();
                }
            });
        },

        _scoresFromSet: function() {
            var self = this;
            var byAccount= {};
            var originalQuestionSet = new DjSet(self.questions);
            var questionSet = originalQuestionSet.clone();

            for ( var i = 0; i < self.selectedMetric.predicates.length; i ++){
                questionSet = DjaoDjinSet.fromPredicate(originalQuestionSet, questionSet, self.selectedMetric.predicates[i]);
            }

            for(var h = 0; h < self.selectedCohorts.length ; h ++){
                var cohort = self.selectedCohorts[h];

                var originalAccounts = new DjSet(self.accounts);
                var accountSet = originalAccounts.clone();

                for ( var i = 0; i < cohort.predicates.length; i ++){
                    accountSet = DjaoDjinSet.fromPredicate(originalAccounts, accountSet, cohort.predicates[i]);
                }

                var correctAnswerCount = 0;
                var matchingQuestionCount = 0;
                for(var i = 0; i < self.samples.length; i ++){
                    var sample = self.samples[i];

                    if ( !accountSet.contains(sample.account)){
                        continue;
                    }


                    for (var j = 0; j < sample.answers.length; j ++){
                        var answer = sample.answers[j];
                        if ( !questionSet.contains(answer.question) ){
                            continue;
                        }

                        matchingQuestionCount += 1;
                        if ( answer.text == answer.question.correct_answer ){
                            correctAnswerCount ++;
                        }
                    }
                }
                var ratioCorrect;
                if ( matchingQuestionCount == 0 ){
                    ratioCorrect = 0;
                }else{
                    ratioCorrect = 1.0 * correctAnswerCount / matchingQuestionCount;
                }
                byAccount[cohort.title] = ratioCorrect * 100;
            }
            self.scores = byAccount;
        },

        updateChart: function() {
            var self = this;
            var chartValues = [];
            var total = 0;
            var count = 0;
            for( var i = 0; i < self.selectedCohorts.length; i++ ) {
                var cohort = self.selectedCohorts[i];
                var score = self.scores[cohort.slug] || 0.0;
                var likelyMetricUrl = null;
                if( cohort.likely_metric ) {
                    likelyMetricUrl = cohort.likely_metric;
                }
                chartValues.push({
                    "likely_metric": likelyMetricUrl,
                    "label": cohort.title,
                    "value": score
                });
                total += score;
                ++count;
            }

            if( chartValues.length === 0 ) {
                chartValues.push({
                    "label": "no portfolio",
                    "value": 0
                });
            }

            var aggregates = [];
            for( var i = 0; i < self.aggregates.length; i++ ) {
                var aggregate = self.aggregates[i];
                var score = self.aggregateScores[aggregate.slug] || 0.0;
                aggregates.push({
                    "label": aggregate.title,
                    "value": score
                });
            }

            var chartData = [{
                "values": chartValues,
                "aggregates": [[{"values": aggregates}]]
            }];

            nv.addGraph(function() {
                var chart = nv.models.matrixChart()
                    .x(function(d) { return d.label })
                    .y(function(d) { return d.value })
                    .staggerLabels(true) // Too many bars and not enough room?
                                         // Try staggering labels.
                    .duration(350)
                    .yDomain([0, 100])
                    .valueFormat(d3.format(',.1f'))
                    .showValues(self.options.showValues);
                if( self.options.color ) {
                    chart.color(function() { return self.options.color; });
                }
                if( self.options.margin ) {
                    chart.margin(self.options.margin);
                }
                if( self.options.rotateLabels ) {
                    chart.rotateLabels(self.options.rotateLabels);
                }

                var svgContainer = self.$element.find(".chart");
                svgContainer.empty().append('<svg>');
                d3.select(svgContainer.find("svg")[0])
                    .datum(chartData)
                    .call(chart);

                nv.utils.windowResize(chart.update);

                return chart;
            });
        },
    };

    $.fn.djmatrixChart = function(options) {
        var opts = $.extend( {}, $.fn.djmatrixChart.defaults, options );
        return this.each(function() {
            if (!$.data($(this), "djmatrixChart")) {
                $.data($(this), "djmatrixChart", new DJMatrixChart(this, opts));
            }
        });
    };

    $.fn.djmatrixChart.defaults = {
        data: null,
        selection_element: null,
        editable_filter_api: null,
        matrix_api: null,
        showValues: true,
        color: null,
        margin: null,
        rotateLabels: 0
    };

})(jQuery);

