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
var DjaoDjinSet = (function () {
    "use strict";

    var DjaoDjinSet = {};

    var operators = [
        {'name': 'equals'     , 'fn': function (a , b) { return a == b }}         ,
        {'name': 'startsWith' , 'fn': function (a , b){ return a.startsWith(b) }} ,
        {'name': 'endsWith'   , 'fn': function (a , b){ return a.endsWith(b) }}   ,
        {'name': 'contains'   , 'fn': function (a , b) { return a.indexOf(b) != -1 }}
    ];
    DjaoDjinSet.operators = operators;

    function Category(title, slug, predicates){
        this.title = title;
        this.slug = slug;
        this.predicates = predicates;
    }
    DjaoDjinSet.Category = Category;


    function Predicate(operator, operand, field, selector){
        this.operator = operator;
        this.operand = operand;
        this.field = field;
        this.selector = selector;
    }
    DjaoDjinSet.Predicate = Predicate;


    function DjSet(l){
        this.key = DjSet.CATEGORIZATION_ID;
        this.key_counter = 0;
        this.items = {};
        if ( l ){
            for ( var i = 0; i < l.length; i ++){
                this.add(l[i]);
            }
        }
    }
    DjSet.CATEGORIZATION_ID = 'id';
    
    DjaoDjinSet.DjSet = DjSet;

    DjSet.prototype.add = function(obj){

        if ( !obj[this.key] ){
            this.key_counter += 1;
            obj[this.key] = this.key_counter;
        }
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
        var clone = new DjSet();
        clone.key = this.key;
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

    function fromPredicate(originalData, data, predicate){
        var operator_fn;
        for ( var j = 0; j < operators.length; j ++){
            if ( predicate.operator == operators[j].name ){
                operator_fn = operators[j].fn;
            }
        }

        var predicate_fn = function(x){
            return operator_fn(new String(x[predicate.field]), predicate.operand);
        }

        var selector = predicate.selector;
        if ( predicate.selector == 'removematching'){

            var toRemove = data.array().filter(predicate_fn);
            for ( var j = 0; j < toRemove.length; j ++){
                data.remove(toRemove[j]);
            }
        }else if (predicate.selector == 'reinclude'){
            data.union(originalData.array().filter(predicate_fn));
        }else if ( predicate.selector == 'keepmatching'){
            data = new DjSet(data.array().filter(predicate_fn));
        }else if ( predicate.selector == 'includeall'){
            data = originalData.clone();
        }else if ( predicate.selector == 'removeall'){
            data = new DjSet();
        }else{
            // console.log('unknown filter type ' + selector );
        }

        return data;

    }
    DjaoDjinSet.fromPredicate = fromPredicate;

    return DjaoDjinSet;
}());
