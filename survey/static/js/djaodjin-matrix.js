(function ($) {
    "use strict";

    var DjSet = DjaoDjinSet.DjSet;

    /** Matrix Chart
        <div id="#_chart_">
          <div>
            <input class="cohort" type="checkbox" name="cohorts">
          </div>
          <div>
            <input class="metric" type="radio" name="metric">
          </div>
        </div>
     */
    function DJMatrixChart(el, options){
        this.element = el;
        this.$element = $(el);
        this.options = options;

        this.responses = [];
        this.portfolios = [];
        this.accounts = [];
        this.questions = [];
        this.questioncategories = [];

        this.selectedQuestionCategory = null;
        this.selectedPortfolios = [];

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
            self.$element.find("[name=\"metric\"]").change(function() {
                self._save();
                self.updateChart();
            });
            self.$element.find("[name=\"cohorts\"]").change(function() {
                self._save();
                self.updateChart();
            });
            self._load();
        },

        _updateSelection: function() {
            var self = this;

            var metricElements = self.$element.find("[name=\"metric\"]:checked");
            if( metricElements.length > 0 ) {
                var $element = $(metricElements[0]);
                var elementVal = $element.val();
                for ( var i = 0; i < self.questioncategories.length; i ++){
                    if ( self.questioncategories[i].slug == elementVal ) {
                        self.selectedQuestionCategory = self.questioncategories[i];
                    }
                }
            }

            var cohortElements = self.$element.find("[name=\"cohorts\"]");
            for( var cohortIdx = 0; cohortIdx < cohortElements.length; ++cohortIdx ) {
                var $element = $(cohortElements[cohortIdx]);
                var elementVal = $element.val();
                if( $element.is(":checked") ) {
                    var found = -1;
                    for ( var idx = 0 ; idx < self.selectedPortfolios.length; ++idx ){
                        if( self.selectedPortfolios[idx].slug === elementVal ) {
                            found = idx;
                        }
                    }
                    if( found < 0 ) {
                        for ( var idx = 0 ; idx < self.portfolios.length; ++idx ){
                            if( self.portfolios[idx].slug === elementVal ) {
                                self.selectedPortfolios.push(self.portfolios[idx]);
                            }
                        }
                    }
                } else {
                    var found = -1;
                    for ( var idx = 0 ; idx < self.selectedPortfolios.length; ++idx ){
                        if( self.selectedPortfolios[idx].slug === elementVal ) {
                            found = idx;
                        }
                    }
                    if( found >= 0 ) {
                        self.selectedPortfolios.splice(found, 1);
                    }
                }
            }
        },

        _load: function() {
            var self = this;
            $.ajax({
                method: "GET",
                url: self.options.portfolio_api + "?q=cohort",
                datatype: "json",
                contentType: "application/json; charset=utf-8",
                success: function(data) {
//                    self.accounts = data.results;
                    self.portfolios = data.results;
                    self._updateSelection();
                    self.updateOptions();
                }
            });

            $.ajax({
                method: "GET",
                url: self.options.portfolio_api + "?q=metric",
                datatype: "json",
                contentType: "application/json; charset=utf-8",
                success: function(data) {
//                    self.questions = response['objects'];
                    self.questioncategories = data.results;
                    self._updateSelection();
                    self.updateOptions();
                }
            });

            $.ajax({
                method: "GET",
                url: self.options.matrix_api,
                datatype: "json",
                success: function(data) {
                    self.scores = data.scores;
                    self.updateChart();
                    $('#status').remove();
                }
            });
        },

        _save: function() {
            var self = this;
            self._updateSelection();
            var data = {
                title: self.$element.find("[name=\"title\"]").val(),
                cohorts: self.selectedPortfolios
            };
            if( self.selectedQuestionCategory ) {
                data['metric'] = self.selectedQuestionCategory;
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

        updateOptions: function() {
            var self = this;
            return; // XXX

            var $questioncategories = self.$element.find("[name=\"questioncategory\"]");
            $questioncategories.empty();
            for ( var i = 0; i < self.questioncategories.length; i ++){
                var $option = $('<option/>');
                var qc = self.questioncategories[i];
                $option.text(qc.title);
                $option.attr('value', qc.slug);
                $questioncategories.append($option);
            }

            var $portfolios = self.$element.find("[name=\"portfolios\"]");
            $portfolios.empty();
            for ( var i = 0; i < self.portfolios.length; i ++){
                var $option = $('<option/>');
                var portfolio = self.portfolios[i];
                $option.attr('value', portfolio.slug);
                $option.text(portfolio.title);
                $portfolios.append($option);
            }
        },

        /** This function will recompute the scores by applying the filters
            on a Response set on the client in Javascript.

            (Currently not used)
         */
        scoresFromSet: function() {
            var byUser= {};
            var originalQuestionSet = new DjSet(self.questions);
            var questionSet = originalQuestionSet.clone();

            for ( var i = 0; i < self.selectedQuestionCategory.predicates.length; i ++){
                questionSet = DjaoDjinSet.fromPredicate(originalQuestionSet, questionSet, self.selectedQuestionCategory.predicates[i]);
            }

            for(var h = 0; h < self.selectedPortfolios.length ; h ++){
                var portfolio = self.selectedPortfolios[h];

                var originalAccounts = new DjSet(self.accounts);
                var accountSet = originalAccounts.clone();

                for ( var i = 0; i < portfolio.predicates.length; i ++){
                    accountSet = DjaoDjinSet.fromPredicate(originalAccounts, accountSet, portfolio.predicates[i]);
                }

                var correctAnswerCount = 0;
                var matchingQuestionCount = 0;
                for(var i = 0; i < self.responses.length; i ++){
                    var response = self.responses[i];

                    if ( !accountSet.contains(response.user)){
                        continue;
                    }


                    for (var j = 0; j < response.answers.length; j ++){
                        var answer = response.answers[j];
                        if ( !questionSet.contains(answer.question) ){
                            continue;
                        }

                        matchingQuestionCount += 1;
                        if ( answer.body == answer.question.correct_answer ){
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
                byUser[portfolio.title] = ratioCorrect * 100;
            }
            self.scores = byUser;
        },

        updateChart: function() {
            var self = this;
            var chartValues = [];
            var aggregates = [{"label": "Goal 75%" + Math.random(),
                               "value": 75}];
            var total = 0;
            var count = 0;
            for ( var k in self.scores ){
                chartValues.push({
                    "label": k,
                    "value": self.scores[k]
                });
                total += self.scores[k];
                count ++;
            }

            var avg = 1.0 * total / count;
            aggregates.push({"label": "Average " + d3.format(',.1f')(avg) + '%',
                             "value": avg });
            var chartData = [{
                "values": chartValues,
                "aggregates": aggregates
            }];

            nv.addGraph(function() {
                var chart = nv.models.matrixChart()
                    .x(function(d) { return d.label })    //Specify the data accessors.
                    .y(function(d) { return d.value })
                    .staggerLabels(true)    //Too many bars and not enough room? Try staggering labels.
                    .showValues(true)       //...instead, show the bar value right on top of each bar.
                    .duration(350)
                    .yDomain([0, 100])
                    .valueFormat(d3.format(',.1f'));

                d3.select('#chart svg')
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
        portfolio_api: null,
        matrix_api: null
    };

})(jQuery);

