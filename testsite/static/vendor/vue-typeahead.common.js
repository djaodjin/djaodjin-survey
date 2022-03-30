'use strict';

//var TypeAhead = Vue.component('typeahead', {
var TypeAhead = Vue.extend({
//  template: '<div><div><i class="fa fa-spinner fa-spin" v-if="loading"></i><template v-else><i class="fa fa-search" v-show="isEmpty"></i><i class="fa fa-times" v-show="isDirty" @click="reset"></i></template><input type="text" placeholder="..." autocomplete="off" v-model="query" @keydown.down="down" @keydown.up="up" @keydown.enter="hit" @keydown.esc="reset" @blur="reset" @input="update"/><ul v-show="hasItems"><li v-for="(item, $item) in items" :class="activeClass($item)" @mousedown="hit" @mousemove="setActive($item)"><span v-text="item.name"></span></li></ul></div></div>',

  data: function data() {
    return {
      items: [],
      query: '',
      current: -1,
      loading: false,
      selectFirst: false,
      queryParamName: 'q'
    };
  },


  computed: {
    hasItems: function hasItems() {
      return this.items.length > 0;
    },
    isEmpty: function isEmpty() {
      return !this.query;
    },
    isDirty: function isDirty() {
      return !!this.query;
    }
  },

  methods: {
    update: function update() {
      var _this = this;

      this.cancel();

      if (!this.query) {
        return this.reset();
      }

      if (this.minChars && this.query.length < this.minChars) {
        return;
      }

      this.loading = true;

      this.fetch().then(function (response) {
        if (response && _this.query) {
          var data = response.data.results;
          data = _this.prepareResponseData ? _this.prepareResponseData(data) : data;
          _this.items = _this.limit ? data.slice(0, _this.limit) : data;
          _this.current = -1;
          _this.loading = false;

          if (_this.selectFirst) {
            _this.down();
          }
        }
      });
    },
    fetch: function fetch() {
      var _this2 = this;

      if (!this.$http) {
        return Vue.util.warn('You need to provide a HTTP client', this);
      }

      if (!this.src) {
        return Vue.util.warn('You need to set the `src` property', this);
      }

      var params = {}
      params[_this2.queryParamName] = _this2.query;
      var request = _this2.$http.get(_this2.src, {params: params});

      return request;
    },
    cancel: function cancel() {},
    reset: function reset() {
      this.items = [];
      this.query = '';
      this.loading = false;
    },
    setActive: function setActive(index) {
      this.current = index;
    },
    activeClass: function activeClass(index) {
      return {
        active: this.current === index
      };
    },
    hit: function hit() {
      if (this.current !== -1) {
        this.onHit(this.items[this.current]);
      }
    },
    up: function up() {
      if (this.current > 0) {
        this.current--;
      } else if (this.current === -1) {
        this.current = this.items.length - 1;
      } else {
        this.current = -1;
      }
    },
    down: function down() {
      if (this.current < this.items.length - 1) {
        this.current++;
      } else {
        this.current = -1;
      }
    },
    onHit: function onHit() {
      Vue.util.warn('You need to implement the `onHit` method', this);
    }
  }
});
