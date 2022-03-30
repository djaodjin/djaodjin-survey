Vue.component('campaign-list', {
    mixins: [
        itemListMixin
    ],
    data: function() {
        return {
            url: this.$urls.survey_api_campaign_list,
            params: {
                o: '-created_at'
            },
            newItem: {
                title: ''
            }
        }
    },
    methods: {
        save: function(){
            var vm = this;
            var data = vm.newItem;
            vm.reqPost(vm.url, data,
            function() {
                vm.get();
                vm.newItem = {
                    title: ''
                }
            });
        },
    },
    mounted: function(){
        this.get();
    }
});


Vue.component('portfolios-received-list', {
    mixins: [
        itemListMixin
    ],
    data: function() {
        return {
            url: this.$urls.survey_api_portfolios_received,
            params: {
                o: '-created_at'
            },
        }
    },
    methods: {
        ignore: function(portfolio, index) {
            var vm = this;
            vm.reqDelete(portfolio.api_accept,
            function(resp) { // success
                vm.remove(vm.items, index);
                showMessages(
                    ["You have denied the request(s)."],
                        "success");
            });
        },
        accept: function(portfolio, index) {
            var vm = this;
            vm.reqPost(portfolio.api_accept,
            function(resp) { // success
                vm.remove(vm.requested, index);
                showMessages(
                    ["You have accepted the request(s)."],
                        "success");
            });
        },
    },
    mounted: function(){
        this.get();
    }
});


Vue.component('portfolios-grant-list', {
    mixins: [
        itemListMixin
    ],
    data: function() {
        return {
            url: this.$urls.survey_api_portfolios_grants,
            params: {
                o: '-created_at'
            },
            grant: {
                grantee: {
                    email: ""
                },
                message: "",
                accounts: [],
            }
        }
    },
    methods: {
        // `this` inside methods points to the Vue instance
        // `event` is the native DOM event
        addAccount: function(dataset, newAccount) {
            var vm = this;
            newAccount.campaign = vm.campaign;
            dataset.push(newAccount);
            vm.$refs.account.reset();
            return false;
        },
        removeAccount: function(dataset, index) {
            dataset.splice(index, 1);
            return false;
        },
        addGrantee: function(grantees, newGrantee) {
            var vm = this;
            if( (typeof newGrantee.slug === 'undefined') && !newGrantee.email ) {
                showErrorMessages("Sorry, we cannot find an e-mail address for "
                                  + newGrantee.full_name);
            } else {
                vm.grant.grantee = newGrantee;
            }
            return false;
        },
        _preparePortfolios: function(grant) {
            var portfolios = {};
            portfolios.grantee = {
                email: grant.grantee.email,
                full_name: grant.grantee.full_name
            };
            if( grant.grantee.message ) {
                portfolios.message = grant.grantee.message;
            }
            if( grant.accounts.length > 0 ) {
                portfolios.accounts = [];
                for( var idx = 0; idx < grant.accounts.length; ++idx ) {
                    portfolios.accounts.push(grant.accounts[idx].slug);
                }
            }
            return portfolios;
        },
        submitGrants: function() {
            var vm = this;
            var portfolios = vm._preparePortfolios(vm.grant);
            vm.reqPost(vm.url, portfolios,
            function(resp) { // success
                showMessages(
                    ["Your porfolio grant was successfully sent."],
                    "success");
            });
        },
    },
    mounted: function(){
        this.get();
    }
});


Vue.component('portfolios-request-list', {
    mixins: [
        itemListMixin
    ],
    data: function() {
        return {
            url: this.$urls.survey_api_portfolios_requests,
            params: {
                o: '-created_at'
            },
            request: {
                message: null,
                accounts: [],
            }
        }
    },
    methods: {
        // `this` inside methods points to the Vue instance
        // `event` is the native DOM event
        addAccount: function(dataset, newAccount) {
            var vm = this;
            newAccount.is_new = true;
            newAccount.full_name = "ukwn";
            dataset.push(newAccount);
            vm.$refs.account.reset();
            return false;
        },
        removeAccount: function(dataset, index) {
            dataset.splice(index, 1);
            return false;
        },
        submitRequests: function() {
            var vm = this;
            vm.reqPost(vm.url, vm.request,
            function(resp) { // success
                showMessages(
                    ["Your porfolio request(s) was successfully sent."],
                    "success");
                vm.requests = [];
            });
        },
    },
    mounted: function(){
        this.get();
    }
});


var AccountTypeAhead = Vue.component('account-typeahead', TypeAhead.extend({
  props: ['dataset'],
  data: function data() {
    return {
      src: this.$urls.api_account_candidates,
      items: [],
      query: '',
      current: -1,
      loading: false,
      selectFirst: false,
      queryParamName: 'q'
    };
  },
  methods: {
    clear: function() {
      this.items = [];
      this.current = -1;
      this.loading = false;
    },

    search: function() {
      var vm = this;
      vm.loading = true;
      vm.fetch().then(function (resp) {
        if (resp && vm.query) {
          var data = resp.data.results;
          data = vm.prepareResponseData ? vm.prepareResponseData(data) : data;
          if( data.length > 0 ) {
              vm.onHit(data[0]);
          } else {
              vm.onHit({email: vm.query});
          }
          vm.loading = false;
        }
      });
    },

    setActiveAndHit: function(item) {
      var vm = this;
      vm.setActive(item);
      vm.hit();
    },

    hit: function hit() {
      var vm = this;
      if( vm.current !== -1 ) {
        vm.onHit(vm.items[vm.current]);
      } else {
        vm.search();
      }
    },

    onHit: function onHit(newItem) {
      var vm = this;
      vm.$emit('selectitem', vm.dataset, newItem);
/*XXX
      if( typeof newItem.full_name !== 'undefined' ) {
          vm.query = newItem.full_name;
      } else {
          vm.query = newItem;
      }
*/
      vm.reset();
      vm.clear();
    }
  }
}));


Vue.component('grantee-typeahead', AccountTypeAhead.extend({
  props: ['dataset'],
  data: function data() {
    return {
      src: this.$urls.api_account_candidates,
      items: [],
      query: '',
      current: -1,
      loading: false,
      selectFirst: false,
      queryParamName: 'q',
      selectedItem: {
          email: "",
          message: ""
      },
      unregistered: false
    };
  },
  methods: {

    onHit: function onHit(newItem) {
      var vm = this;
      if( newItem.slug ) {
        vm.$emit('selectitem', vm.dataset, newItem);
        vm.reset();
      } else {
        vm.selectedItem.email = vm.query;
        vm.unregistered = true;
      }
    },
    submitInvite: function() {
      var vm = this;
      vm.$emit('selectitem', vm.dataset, vm.selectedItem);
    },
  }
}));


Vue.component('grant-allowed-typeahead', AccountTypeAhead.extend({
  data: function data() {
    return {
      src: this.$urls.api_grant_allowed_candidates,
      items: [],
      query: '',
      current: -1,
      loading: false,
      selectFirst: false,
      queryParamName: 'q'
    };
  }
}));
