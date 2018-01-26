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

    /**

     <style>
     .dj-predicate-template {
       display: none; // Templates are stored in DOM without being UI elements.
     }
     </style>

     <div>
       <input type="text" name="title">
       <button class="save">Update</button>
       <div class="dj-predicates">
           ... This is where the filter predicates are presented ...
           <div class="dj-predicate-template" style="display:none;">
             <select class="operator"></select>
             <select class="operand"></select>
             <select class="field"></select>
             <select class="selector"></select>
             <button class="delete"></button>
           </div>
           <button class="add-predicate">Add predicate</button>
       </div>
       <table class="dj-table">
           ... This is where the filtered data will be presented ...
       </table>
     </div>
    */
    function Djcategorize(el, options){
        this.element = $(el);
        this.options = options;
        this.data = [];
        this.categories = [];
        this.selectedCategoryIndex = 0;
        this.dataProperties = [];
        this.init();
    }

    Djcategorize.prototype = {
        init: function(){
            var self = this;
            var $element = $(self.element);
            self.$categoryTitle = $element.find("[name='title']");
            self.$categoryTitle.on('input', function(e){
                self.selectedCategory().title = $(e.target).val();
                self.save();
                self.update();
                return false;
            });

            var $saveButton = $element.find(".save");
            $saveButton.on('click', function(event){
                event.preventDefault();
                self.save();
            });

            var addPredicateButton =  $element.find(".add-predicate");
            addPredicateButton.on('click', function(){
                event.preventDefault();
                self.selectedCategory().predicates.push(new Predicate(
                    'equals', '', self.dataProperties[0] || '',
                    'keepmatching'));
                self.update();
            });

            self._load();
        },

        _csrfToken: function() {
            var self = this;
            if( self.options.csrfToken ) { return self.options.csrfToken; }
            return getMetaCSRFToken();
        },

        _load: function() {
            var self = this;
            $.ajax({
                method: "GET",
                url: self.options.objects_api,
                datatype: "json",
                contentType: "application/json; charset=utf-8",
                success: function(data) {
                    self.data = data.results;
                    if( data.editable_filter ) {
                        self.categories = [data.editable_filter];
                        self._updateCategories();
                    }
                    self.updateDataProperties();
                    self.update();
                },
                error: function(resp) {
                    showErrorMessages(resp);
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
                method: "PUT",
                url: self.options.editable_filter_api,
                data: JSON.stringify(category),
                datatype: "json",
                contentType: "application/json; charset=utf-8",
                success: function(category, resp){
                    if ( !category.slug ){
                        category.slug = resp.slug;
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
            var $element = $(self.element);

            var originalData = new DjSet(self.data);
            var resultData = originalData.clone();
            for ( var i = 0; i < self.selectedCategory().predicates.length; i ++){
                resultData = fromPredicate(originalData, resultData, self.selectedCategory().predicates[i]);

            }

            var $table = $element.find(".dj-table");
            $table.html("");

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
        },

        /** Update the dropdown of available filters.
         */
        _updateCategories: function() {
            var self = this;
            var $categories = $(self.element).find(".categories");
            if( $categories.length > 0 ) {
                var $categoryElems = $categories.children('option');
                for (var i = 0; i < self.categories.length; i ++){
                    var category = self.categories[i];
                    var $elem;
                    if ( i >= $categoryElems.length ){
                        $elem = $('<option/>');
                        $elem.attr('value', i);
                        $categories.append($elem);
                    }else{
                        $elem = $categoryElems.eq(i);
                    }
                    $elem.text(category.title);
                }
                for ( var i = self.categories.length; i < $categoryElems.length ; i ++){
                    $categoryElems.get(i).remove();
                }
                $categories.val(self.selectedCategoryIndex);
            }
            self.$categoryTitle.val(self.selectedCategory().title);
        },

        /** Update the list of predicates.
         */
        _updatePredicates: function(predicates) {
            var self = this;
            var predicateContainer = $(self.element).find(".dj-predicates");
            var $predicateElems = predicateContainer.children('.predicate');
            var predicateElemTemplate =  predicateContainer.find(".dj-predicate-template");
            for ( var i = 0; i < predicates.length; ++i ){
                var predicate = predicates[i];
                var $elem;
                if( i >= $predicateElems.length ) {
                    /* Let's add a ui element when the new list is longer. */
                    $elem = predicateElemTemplate.clone();
                    $elem.removeClass("dj-predicate-template").addClass("predicate");
                    predicateContainer.append($elem);
                    $elem.find('.delete').on('click', function(i, $elem){
                        predicates.splice(i, 1);
                        $elem.remove();
                        self.save();
                        self.update();
                    }.bind(null, i, $elem));

                    var onUpdate = function(predicate, prop){
                        return function(e){
                            predicate[prop] = $(e.target).val();
                            return false;
                        };
                    };

                    $elem.find('.operator').on('input',
                        onUpdate(predicate,'operator'));
                    $elem.find('.operand').on('input',
                        onUpdate(predicate,'operand'));
                    $elem.find('.field').on('input',
                        onUpdate(predicate,'field'));
                    $elem.find('.selector').on('input',
                        onUpdate(predicate,'selector'));
                    $elem.find('input').on('input', function(){
                        self.save();
                        self.update();
                    });
                    $elem.find('select').on('input', function(){
                        self.save();
                        self.update();
                    });

                    var $properties = $elem.find('.field');
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
                } else {
                    $elem = $predicateElems.eq(i);
                }
                /* update the ui element. */
                $elem.find('.operator').val(predicate.operator);
                $elem.find('.operand').val(predicate.operand);
                $elem.find('.field').val(predicate.field);
                $elem.find('.selector').val(predicate.selector);
            }

            /* Let's remove extraneous ui elements when the new list
               is shorter. */
            for( var i = predicates.length; i < $predicateElems.length ; ++i ) {
                $predicateElems.get(i).remove();
            }
        },

        update: function(){
            var self = this;
            self._updatePredicates(self.selectedCategory().predicates);
            self.updateTable();
        }
    }

    $.fn.djcategorize = function(options) {
        var opts = $.extend( {}, $.fn.djcategorize.defaults, options );
        return this.each(function() {
            if (!$.data($(this), "djcategorize")) {
                $.data($(this), "djcategorize", new Djcategorize(this, opts));
            }
        });
    };

    $.fn.djcategorize.defaults = {
        editable_filter_api: null,
        objects_api: null
    };
})(jQuery);
