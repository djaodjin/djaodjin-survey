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

    var DjSet = DjaoDjinSet.DjSet;
    var operators = DjaoDjinSet.operators;
    var Category = DjaoDjinSet.Category;
    var Predicate = DjaoDjinSet.Predicate;
    var fromPredicate = DjaoDjinSet.fromPredicate;

    function Djcategorize(el, options){
        this.element = $(el);
        this.options = options;
        this.init();
    }

    Djcategorize.prototype = {
        init: function(){
            var self = this;

            self.data = [];


            self.categories = [new Category('title', null, [])];
            self.selectedCategoryIndex = 0;

            self.$addCategoryButton = $('<button/>');
            self.$addCategoryButton.text('New');
            self.$addCategoryButton.on('click', function(){
                self.categories.push(new Category('title', null, []));
                self.selectedCategoryIndex = self.categories.length - 1;
                self.update();
            })
            self.element.append(self.$addCategoryButton);


            self.$categories = $('<select></select>');
            self.$categories.on('input', function(e){
                self.selectedCategoryIndex=parseInt($(e.target).val(),10);
                self.update();
            });
            self.element.append(self.$categories);

            self.element.append('<br/>');
            self.$categoryTitle = $('<input type="text" />');
            self.$categoryTitle.on('input', function(e){
                self.selectedCategory().title = $(e.target).val();
                self.update();
                return false;
            });
            self.element.append(self.$categoryTitle);

            self.$saveButton = $('<button>Save</button>');
            self.$saveButton.on('click', function(){
                self.save();
            });
            self.element.append(self.$saveButton);
            self.$saveButton.wrap('<div/>')

            self.addPredicateButton = $('<button/>');
            self.addPredicateButton.text('Add Predicate');
            self.element.append(self.addPredicateButton);
            self.addPredicateButton.on('click', function(){
                self.selectedCategory().predicates.push(new Predicate('equals', '', self.dataProperties[0] || '', 'removematching'));
                self.update();
            });

            self.predicateContainer = $('<div/>');
            self.element.append(self.predicateContainer);

            self.dataProperties = [];
            self.updateDataProperties();

            self.$tableContainer = $('<div/>');
            self.element.append(self.$tableContainer);

            self.resultData = new DjSet(self.data);
            self.updateTable();




            $.ajax({
                method: "GET",
                url: self.options.api,
                datatype: "json",
                contentType: "application/json; charset=utf-8",
                success: function(response) {
                    self.data = response['objects'];

                    self.resultData = new DjSet(self.data);
                    if (response.categories.length > 0){
                        self.categories = response['categories'];
                    }

                    self.updateDataProperties();
                    self.update();
                }
            });



        },
        selectedCategory: function (){
            var self = this;
            return self.categories[self.selectedCategoryIndex];
        },
        save: function(){
            var self = this;

            var category = self.selectedCategory();
            $.ajax({
                method: "POST",
                url: self.options.api,
                data: JSON.stringify(category),
                datatype: "json",
                contentType: "application/json; charset=utf-8",
                success: function(category,response){
                    if ( !category.slug ){
                        category.slug = response.slug;
                    }
                }.bind(null, category)
            });

        },
        updateDataProperties: function(){
            var self = this;
            self.dataProperties = [];
            var propSet = {};
            for ( var i = 0 ; i < self.data.length; i ++){
                var datum = self.data[i];
                for (var k in datum){
                    if ( !propSet[k] && k != DjSet.CATEGORIZATION_ID ){
                        self.dataProperties.push(k);
                        propSet[k] = true;
                    }
                }
            }
        },
        updateTable: function(){
            var self = this;

            var originalData = new DjSet(self.data);
            var resultData = originalData.clone();

            for ( var i = 0; i < self.selectedCategory().predicates.length; i ++){
                resultData = fromPredicate(originalData, resultData, self.selectedCategory().predicates[i]);

            }

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

            var dataArray = self.data;
            for ( var j = 0 ; j < dataArray.length; j ++){
                var datum = dataArray[j];
                var $tr = addRow(datum);
                if ( originalData.contains(datum) && !resultData.contains(datum) ){
                    $tr.addClass('danger');
                }
            }

            self.$tableContainer.html($table);

        },
        update: function(){
            var self = this;

            var $categoryElems = self.$categories.children('option');
            for (var i = 0; i < self.categories.length; i ++){
                var category = self.categories[i];
                var $elem;
                if ( i >= $categoryElems.length ){
                    $elem = $('<option/>');
                    $elem.attr('value', i);

                    self.$categories.append($elem);
                }else{
                    $elem = $categoryElems.eq(i);
                }

                $elem.text(category.title);
            }
            for ( var i = self.categories.length; i < $categoryElems.length ; i ++){
                $categoryElems.get(i).remove();
            }

            self.$categories.val(self.selectedCategoryIndex);
            self.$categoryTitle.val(self.selectedCategory().title);

            var $predicateElems = self.predicateContainer.children('.predicate');
            var data = new DjSet(self.data);
            for ( var i = 0; i < self.selectedCategory().predicates.length; i ++){
                var predicate = self.selectedCategory().predicates[i];
                var $elem;
                if ( i >= $predicateElems.length ){
                    $elem = $('<div class="predicate"><select class="filterType"><option value="removematching">Remove matching</option><option value="reinclude">Reinclude matching from full set</option><option value="keepmatching">Keep Matching</option><option value="includeall">Include all</option><option value="removeall">Remove all</option></select><select class="property" ></select><select class="operator" ></select><input class="operand" type="text"/><button>Remove</button><br/>');
                    self.predicateContainer.append($elem);

                    $elem.find('button').on('click', function(i,$elem){

                        self.selectedCategory().predicates.splice(i,1);
                        $elem.remove();
                        self.update();

                    }.bind(null,i, $elem));

                    var onUpdate = function(predicate, prop){
                        return function(e){
                            predicate[prop] = $(e.target).val();
                            return false;
                        };
                    };

                    $elem.find('.operator').on('input', onUpdate(predicate,'operator'));
                    $elem.find('.operand').on('input', onUpdate(predicate,'operand'));
                    $elem.find('.property').on('input', onUpdate(predicate,'property'));
                    $elem.find('.filterType').on('input', onUpdate(predicate,'filterType'));

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
                    $elem = $predicateElems.eq(i);
                }

                $elem.find('.operator').val(predicate.operator);
                $elem.find('.operand').val(predicate.operand);
                $elem.find('.property').val(predicate.property);
                $elem.find('.filterType').val(predicate.filterType);




            }

            for ( var i = self.selectedCategory().predicates.length; i < $predicateElems.length ; i ++){
                $predicateElems.get(i).remove();
            }
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
