jQuery(document).ready(function($) {
    var DjSet = DjaoDjinSet.DjSet;

    var responses = [];
    var portfolios = [];
    var accounts = [];
    var questions = [];
    var questioncategories = [];

    function updateOptions(){
        var $questioncategories = $('#questioncategory');
        $questioncategories.empty();
        for ( var i = 0; i < questioncategories.length; i ++){
            var $option = $('<option/>');
            var qc = questioncategories[i];
            $option.text(qc.title);
            $option.attr('value', qc.slug);
            $questioncategories.append($option);
        }
        var $portfolios = $('#portfolio');
        $portfolios.empty();
        for ( var i = 0; i < portfolios.length; i ++){
            var $option = $('<option/>');
            var portfolio = portfolios[i];
            $option.attr('value', portfolio.slug);
            $option.text(portfolio.title);
            $portfolios.append($option);
        }

    }

    $.ajax({
        method: "GET",
        url: portfolio_api,
        datatype: "json",
        contentType: "application/json; charset=utf-8",
        success: function(response) {
            accounts = response['objects'];
            portfolios = response['categories'];
            updateOptions();
        }
    });

    $.ajax({
        method: "GET",
        url: questioncategory_api,
        datatype: "json",
        contentType: "application/json; charset=utf-8",
        success: function(response) {
            questions = response['objects'];
            questioncategories = response['categories'];
            updateOptions();
        }
    });

    $.ajax({
        method: "GET",
        url: "/matrix/api/survey",
        datatype: "json",
        success: function(_responses) {
            responses = _responses;

            updateChart();
        }
    });

    function updateChart(){
        var byUser= {};

        var selectedPortfolios = [];
        var selectedPortfolioSlugs = $('#portfolio').val();
        for ( var i = 0; selectedPortfolioSlugs && i < selectedPortfolioSlugs.length; i ++){
            for ( var j = 0 ; j < portfolios.length; j ++){
                if ( selectedPortfolioSlugs[i] == portfolios[j].slug ){
                    selectedPortfolios.push(portfolios[j]);
                }
            }
        }


        var selectedQuestionCategorySlug = $('#questioncategory').val();
        var selectedQuestionCategory;
        for ( var i = 0; i < questioncategories.length; i ++){
            if ( questioncategories[i].slug == selectedQuestionCategorySlug ){
                selectedQuestionCategory = questioncategories[i];
            }
        }

        var originalQuestionSet = new DjSet(questions);
        var questionSet = originalQuestionSet.clone();

        for ( var i = 0; i < selectedQuestionCategory.predicates.length; i ++){
            questionSet = DjaoDjinSet.fromPredicate(originalQuestionSet, questionSet, selectedQuestionCategory.predicates[i]);
        }


        for(var h = 0; h < selectedPortfolios.length ; h ++){
            var portfolio = selectedPortfolios[h];

            var originalAccounts = new DjSet(accounts);
            var accountSet = originalAccounts.clone();

            for ( var i = 0; i < portfolio.predicates.length; i ++){
                accountSet = DjaoDjinSet.fromPredicate(originalAccounts, accountSet, portfolio.predicates[i]);
            }

            var correctAnswerCount = 0;
            var matchingQuestionCount = 0;
            for(var i = 0; i < responses.length; i ++){
                var response = responses[i];

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
        var chartValues = [];

        var aggregates = [{"label": "Goal 75%" + Math.random(),
                           "value": 75}];

        var total = 0;
        var count = 0;
        for ( var k in byUser ){
            chartValues.push({
                "label": k,
                "value": byUser[k]
            });

            total += byUser[k];
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
                .valueFormat(d3.format(',.1f'))
            ;

            d3.select('#chart svg')
                .datum(chartData)
                .call(chart);

            nv.utils.windowResize(chart.update);

            return chart;
        })
    };

    $('#questioncategory').on('input',function (e){
        updateChart();
    });
    $('#portfolio').on('input',function (e){
        updateChart();
    });

});

