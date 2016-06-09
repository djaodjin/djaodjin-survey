if (!Array.prototype.filter) {
    Array.prototype.filter = function(fun/*, thisArg*/) {
        'use strict';

        if (this === void 0 || this === null) {
            throw new TypeError();
        }

        var t = Object(this);
        var len = t.length >>> 0;
        if (typeof fun !== 'function') {
            throw new TypeError();
        }

        var res = [];
        var thisArg = arguments.length >= 2 ? arguments[1] : void 0;
        for (var i = 0; i < len; i++) {
            if (i in t) {
                var val = t[i];

                // NOTE: Technically this should Object.defineProperty at
                //       the next index, as push can be affected by
                //       properties on Object.prototype and Array.prototype.
                //       But that method's new, and collisions should be
                //       rare, so use the more-compatible alternative.
                if (fun.call(thisArg, val, i, t)) {
                    res.push(val);
                }
            }
        }

        return res;
    };
}

(function ($) {
    "use strict";

    var operators = [
        {'name': 'equals'     , 'fn': function (a , b) { return a == b }}         ,
        {'name': 'startsWith' , 'fn': function (a , b){ return a.startsWith(b) }} ,
        {'name': 'endsWith'   , 'fn': function (a , b){ return a.endsWith(b) }}   ,
        {'name': 'contains'   , 'fn': function (a , b) { return a.indexOf(b) != -1 }}
    ];


    function DjSet(k, l){
        this.key = k;
        this.items = {};
        if ( l ){
            for ( var i = 0; i < l.length; i ++){
                this.add(l[i]);
            }
        }
    }

    DjSet.prototype.add = function(obj){
        this.items[obj[this.key]] = obj;
    }

    DjSet.prototype.remove = function(obj){
        delete this.items[obj[this.key]];
    }

    DjSet.prototype.array = function(){
        var l = [];
        for ( var k in this.items ){
            l.push(this.items[k]);
        }
        return l;
    }    

    DjSet.prototype.union = function(other){
        if ( $.isArray(other) ){
            for ( var i = 0 ; i < other.length; i ++){
                this.add(other[i]);
            }
        }else{
            // assume DjSet
            for ( var k in other){
                this.add(other[k]);
            }
        }
    }

    DjSet.prototype.clone = function(){
        var clone = new DjSet(this.key);
        clone.items = jQuery.extend({}, this.items);
        return clone;
    };

    DjSet.prototype.contains = function(obj){
        return this.items[obj[this.key]];
    }

    DjSet.prototype.difference = function(other){
        var otherSet;
        if ( $.isArray(other) ){
            otherSet = new DjSet(other);
        }else{
            // assume DjSet
            otherSet = other;

        }
        for ( var k in this.items){
            if ( otherSet.contains(this.items[k]) ){
                delete this.items[k];
            }
        }
    }

    DjSet.prototype.intersect = function(other){
        var otherSet;
        if ( $.isArray(other) ){
            otherSet = new DjSet(other);
        }else{
            // assume DjSet
            otherSet = other;

        }
        for ( var k in this.items){
            if ( !otherSet.contains(this.items[k]) ){
                delete this.items[k];
            }
        }
    }

    function Djcategorize(el, options){
        this.element = $(el);
        this.options = options;
        this.init();
    }

    Djcategorize.prototype = {
        init: function(){
            var self = this;

            self.steps = [];


            self.addStepButton = $('<button/>');
            self.addStepButton.text('Add Step');
            self.element.append(self.addStepButton);
            self.addStepButton.on('click', function(){
                self.steps.push('');
                self.update();
            });

            self.stepContainer = $('<div/>');
            self.element.append(self.stepContainer);

            self.dataProperties = [];
            var propSet = {};
            for ( var i = 0 ; i < self.options.data.length; i ++){
                var datum = self.options.data[i];
                for (var k in datum){
                    if ( !propSet[k] ){
                        self.dataProperties.push(k);
                        propSet[k] = true;
                    }
                }
            }

            self.$tableContainer = $('<div/>');
            self.element.append(self.$tableContainer);

            self.resultData = new DjSet(self.options.data_key, self.options.data);
            self.updateTable();

        },

        stringifyData: function(data){
            var self = this;
            var ss = [];
            for ( var i = 0; i < data.length; i ++){
                ss.push(data[i][self.options.name_key]);
            }
            return ss.join(', ');
        },
        updateTable: function(){
            var self = this;
            // expects self.resultData to be set
            var $table = $('<table/>');
            $table.addClass('table');
            $table.addClass('table-striped');
            $table.addClass('table-condensed');

            var $header = $('<tr/>');
            for (var k = 0; k < self.dataProperties.length; k ++){
                var $th = $('<th/>');
                $th.text(self.dataProperties[k]);
                $header.append($th);
            }
            $table.append($header);

            function addRow(datum){
                var $tr = $('<tr/>');
                for (var k = 0; k < self.dataProperties.length; k ++){
                    var prop = self.dataProperties[k];
                    var $td = $('<td/>');
                    $td.text(datum[prop]);
                    $tr.append($td);
                }
                $table.append($tr);
                return $tr;
            }

            var dataArray = self.options.data;
            var data = new DjSet(self.options.data_key, self.options.data);
            for ( var j = 0 ; j < dataArray.length; j ++){
                var datum = dataArray[j];
                var $tr = addRow(datum);
                if ( data.contains(datum) && !self.resultData.contains(datum) ){
                    $tr.addClass('danger');
                }
            }
            
            self.$tableContainer.html($table);
            
        },
        update: function(){
            var self = this;
            
            var $stepElems = self.stepContainer.children('.step');
            var data = new DjSet(self.options.data_key, self.options.data);
            for ( var i = 0; i < self.steps.length; i ++){
                var $elem;
                if ( i >= $stepElems.length ){
                    $elem = $('<div class="step"><select class="addorsubtract"><option value="removematching">Remove matching</option><option value="reinclude">Include matching full set</option><option value="keepmatching">Keep Matching</option><option value="includeall">Include all</option><option value="removeall">Remove all</option></select><select class="property" ></select><select class="operator" ></select><input class="operand" type="text"/><button>Remove</button><br/>');
                    self.stepContainer.append($elem);

                    $elem.find('button').on('click', function(i,$elem){

                        self.steps.splice(i,1);
                        $elem.remove();
                        
                    }.bind(null,i, $elem));

                    $elem.find('input').on('input', function(){
                        self.update();
                    });
                    $elem.find('select').on('input', function(){
                        self.update();
                    });

                    var $properties = $elem.find('.property');
                    for (var j = 0; j < self.dataProperties.length; j ++){
                        var $option = $('<option/>');
                        $option.text(self.dataProperties[j]);
                        $properties.append($option);
                    }

                    var $operators = $elem.find('.operator');
                    for ( var j = 0; j < operators.length; j ++){
                        var operator = operators[j];
                        var $option = $('<option/>');
                        $option.text(operator.name);
                        $operators.append($option);                        
                    }

                         

                }else{
                    $elem = $stepElems.eq(i);
                }
                
                var operator_name = $elem.find('.operator').val();
                var operator_fn;
                for ( var j = 0; j < operators.length; j ++){
                    if ( operator_name == operators[j].name ){
                        operator_fn = operators[j].fn;
                    }
                }

                var operand =  $elem.find('.operand').val();
                var property = $elem.find('.property').val();
                var predicate = function(x){
                    return operator_fn(x[property], operand);
                }

                var previousData = data.clone();
                var filterType = $elem.find('.addorsubtract').val()
                if ( filterType == 'removematching'){

                    var toRemove = data.array().filter(predicate);
                    for ( var j = 0; j < toRemove.length; j ++){
                        data.remove(toRemove[j]);
                    }
                }else if (filterType == 'reinclude'){
                    data.union(self.options.data.filter(predicate));

                }else if ( filterType == 'keepmatching'){
                    data= new DjSet(data.key, data.array().filter(predicate));
                }else if ( filterType == 'includeall'){
                    data = new DjSet(self.options.data_key, self.options.data);
                }else if ( filterType == 'removeall'){
                    data = new DjSet(self.options.data_key);
                }else{
                    // console.log('unknown filter type ' + filterType );
                }

            }

            for ( var i = self.steps.length; i < $stepElems.length ; i ++){
                $stepElems.get(i).remove();
            }
            self.resultData = data;
            self.updateTable();
            
        }

    }

    $.fn.djcategorize = function(options) {
        var opts = $.extend( {}, $.fn.djcategorize.defaults, options );
        return new Djcategorize($(this), opts);
    };

    $.fn.djcategorize.defaults = {

    };
})(jQuery);
