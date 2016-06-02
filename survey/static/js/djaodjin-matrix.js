jQuery(document).ready(function($) {

    $.ajax({
        method: "GET",
        url: "/matrix/api/survey",
        datatype: "json",
        contentType: "application/json; charset=utf-8",
        success: function(response) {
            console.log('responso');
            var data = calculateData(response);
            var chartValues = [];

            var aggregates = [{"label": "Goal 75%",
                               "value": 75}];

            var total = 0;
            var count = 0;
            for ( var k in data ){
                chartValues.push({
                    "label": k,
                    "value": data[k]
                });

                total += data[k];
                count ++;
            }

            var avg = 1.0 * total / count
            aggregates.push({"label": "Average " + (avg + '').substring(0,4) + '%',
                             "value": avg });

            var chartData = [{
                "values": chartValues,
                "aggregates": aggregates
            }];

            updateChart(chartData);
            console.log('chartData');
            console.log(chartData)
        }
    });
});

function calculateData(results){

    var byUser= {};
    
    for(var i = 0; i < results.length; i ++){
        var result = results[i];

        var userId = result.user.email + ' ' + i;

        var correctAnswerCount = 0;
        for (var j = 0; j < result.answers.length; j ++){
            var answer = result.answers[j];
            if ( answer.body == answer.question.correct_answer ){
                correctAnswerCount ++;
            }
        }

        var ratioCorrect = 1.0 * correctAnswerCount / result.answers.length;

        byUser[userId] = ratioCorrect * 100;
    }
    return byUser;
}

function updateChart(chartData){
    nv.addGraph(function() {

        var chart = nv.models.matrixChart()
            .x(function(d) { return d.label })    //Specify the data accessors.
            .y(function(d) { return d.value })
            .staggerLabels(true)    //Too many bars and not enough room? Try staggering labels.
            .showValues(true)       //...instead, show the bar value right on top of each bar.
            .duration(350)
        ;

        d3.select('#chart svg')
            .datum(chartData)
            .call(chart);

        nv.utils.windowResize(chart.update);

        return chart;
    })
};


//Each bar represents a single discrete quantity.
function exampleData() {
 return  [ 
    {
      key: "Cumulative Return",
        aggregates: [
            {"label": "hello",
             "value": 13},
            {"label": "there",
             "value": 32}
        ],
      values: [
        { 
          "label" : "A Label" ,
            "value" : Math.random() * 200
        } , 
        { 
          "label" : "B Label" , 
          "value" : 0
        } , 
        { 
          "label" : "C Label" , 
          "value" : 32.807804682612
        } , 
        { 
          "label" : "D Label" , 
          "value" : 196.45946739256
        } , 
        { 
          "label" : "E Label" ,
          "value" : 0.19434030906893
        } , 
        { 
          "label" : "F Label" , 
          "value" : 98.079782601442
        } , 
        { 
          "label" : "G Label" , 
          "value" : 13.925743130903
        } , 
        { 
          "label" : "H Label" , 
          "value" : 5.1387322875705
        }
      ]
    }
  ]

}



