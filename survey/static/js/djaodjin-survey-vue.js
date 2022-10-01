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
            url_account_base: this.$urls.api_account_candidates,
            params: {
                o: '-created_at'
            },
            getCompleteCb: '_decorateProfiles',
        }
    },
    methods: {
        _decorateProfile: function(item) {
            var vm = this;
            vm.reqGet(vm._safeUrl(vm.url_account_base, item.grantee),
            function(respProfile) {
                item.grantee = respProfile;
            }, function(respProfile) {
                // ok if we cannot find profile information.
            });
        },
        _decorateProfiles: function() {
            var vm = this;
            for( var idx = 0; idx < vm.items.results.length; ++idx ) {
                vm._decorateProfile(vm.items.results[idx]);
            }
        },
        accept: function(portfolio, idx) {
            var vm = this;
            vm.reqPost(portfolio.api_accept,
            function(resp) { // success
                vm.items.results.splice(idx, 1);
                vm.showMessages(
                    ["You have accepted the request(s)."],
                        "success");
            });
        },
        ignore: function(portfolio, idx) {
            var vm = this;
            vm.reqDelete(portfolio.api_accept,
            function(resp) { // success
                vm.items.results.splice(idx, 1);
                vm.showMessages(
                    ["You have denied the request(s)."],
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
    props: {
        defaultSelectedAccounts: {
            type: Array,
            default: function() {
                return [];
            }
        }
    },
    data: function() {
        return {
            url: this.$urls.survey_api_portfolios_grants,
            url_account_base: this.$urls.api_account_candidates,
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
            if( (typeof newGrantee.slug === 'undefined') &&
                !newGrantee.email ) {
// We don't want to scroll back to the top when an invite should be created.
//                showErrorMessages(
//                    "Sorry, we cannot find contact information for " + (
//                    newGrantee.full_name || newGrantee.email);
            } else {
                vm.grant.grantee = newGrantee;
            }
            return false;
        },
        _preparePortfolios: function(grant) {
            var portfolios = {};
            portfolios.grantee = {
                email: grant.grantee.email,
                full_name: (grant.grantee.full_name ||
                    grant.grantee.printable_name)
            };
            if( grant.grantee.slug ) {
                portfolios.grantee.slug = grant.grantee.slug;
            }
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
        _submitPortfolios: function(portfolios) {
            var vm = this;
            vm.reqPost(vm.url, portfolios,
            function(resp) { // success
                vm.showMessages(
                    ["Your porfolio grant was successfully sent."],
                    "success");
            });
        },
        submitGrants: function() {
            var vm = this;
            var portfolios = vm._preparePortfolios(vm.grant);
            if( portfolios.grantee.slug ) {
                vm._submitPortfolios(portfolios);
            } else {
                vm.reqPost(vm.url_account_base, portfolios.grantee,
                function(resp) {
                    var email = portfolios.grantee.email;
                    portfolios.grantee = resp;
                    portfolios.grantee.email = email;
                    vm._submitPortfolios(portfolios);
                });
            }
        },
        ignore: function(portfolio, idx) {
            var vm = this;
            vm.reqDelete(portfolio.api_remove,
            function(resp) { // success
                vm.items.results.splice(idx, 1);
            });
        },
    },
    computed: {
        showAccounts: function() {
            return this.grant.grantee.slug || this.grant.grantee.email;
        }
    },
    mounted: function(){
        var vm = this;
        vm.get();
        if( vm.defaultSelectedAccounts ) {
            vm.grant.accounts = vm.defaultSelectedAccounts;
        }
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
                vm.showMessages(
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
      url: this.$urls.api_account_candidates,
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
    // Almost identical to `update` except we call onHit.
    search: function() {
        var vm = this;
        vm.cancel();
        if (!vm.query) {
            return vm.reset();
        }
        if( vm.minChars && vm.query.length < vm.minChars ) {
            return;
        }
        vm.loading = true;
        var params = {};
        params[vm.queryParamName] = vm.query;
        vm.reqGet(vm.url, params,
        function (resp) {
            if (resp && vm.query) {
                var data = resp.results;
                data = vm.prepareResponseData ? vm.prepareResponseData(data) : data;
                vm.items = vm.limit ? data.slice(0, vm.limit) : data;
                vm.current = -1;
                vm.loading = false;
                if( data.length > 0 ) {
                    vm.onHit(data[0]);
                } else {
                    vm.onHit({email: vm.query});
                }
            }
        }, function() {
            // on failure we just do nothing. - i.e. we don't want a bunch
            // of error messages to pop up.
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
  props: ['dataset', 'defaultMessage', 'showAccounts'],
  data: function data() {
    return {
      url: this.$urls.api_account_candidates,
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
        vm.selectedItem.message = vm.defaultMessage;
        vm.unregistered = true;
        vm.$nextTick(function() {
            vm.$refs.fullName.focus();
        });
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
      url: this.$urls.api_grant_allowed_candidates,
      items: [],
      query: '',
      current: -1,
      loading: false,
      selectFirst: false,
      queryParamName: 'q'
    };
  }
}));


// shows comparaison matrices
Vue.component('compare-dashboard', {
    mixins: [
        itemMixin
    ],
    data: function() {
        return {
            url: this.$urls.matrix_api,
            colors: this.$colorsTheme ? this.$colorsTheme : ['#f0ad4e'],
            getCb: 'updateCharts',
            charts: {}
        }
    },
    methods: {
        updateCharts: function(resp) {
            var vm = this;
            vm.item = resp;
            vm.itemLoaded = true;
            var chartsData = {};
            for( var tdx = 0; tdx < resp.length; ++tdx ) {
                var table = resp[tdx];
                var labels = [];
                var datasets = [];
                var chartKey = table.slug;
                for( var idx = 0; idx < table.cohorts.length; ++idx ) {
                    labels.push(table.cohorts[idx].title);
                }
                var data = [];
                for( var key in table.values ) {
                    if( table.values.hasOwnProperty(key) ) {
                        data.push(table.values[key]);
                    }
                }
                datasets.push({
                    label: table.title,
                    backgroundColor: vm.colors,
                    borderColor: vm.colors,
                    data: data
                });
                const chartLookup = chartKey.startsWith('aggregates-') ? chartKey.substr(11) : chartKey;
                if( chartsData[chartLookup] ) {
                    /*
                    datasets['type'] = 'line'
                    chartsData[chartLookup].datasets = [
                        chartsData[chartLookup].datasets,
                        datasets,
                    ];
                    */
                } else {
                    datasets['type'] = 'bar'
                    chartsData[chartLookup] = {
                        datasets: datasets,
                        labels: labels,
                    };
                }
            }
            for( var chartKey in chartsData ) {
                if( !chartsData.hasOwnProperty(chartKey) ) continue;

                var table = chartsData[chartKey];
                if( vm.charts[chartKey] ) {
                    vm.charts[chartKey].destroy();
                }
                const element = document.getElementById(chartKey);
                if( element ) {
                    if( table.length >= 2 ) {
                        vm.charts[chartKey] = new Chart(
                            element,
                            {
                                data: table,
                                options: {
                                    responsive: true,
                                    plugins: {
                                        legend: {
                                            display: false,
                                        },
                                        title: {
                                            display: false,
                                            text: table.title
                                        }
                                    }
                                },
                            },

                        );
                    } else {
                        vm.charts[chartKey] = new Chart(
                            element,
                            {
                                type: 'bar',
                                data: table,
                                options: {
                                    responsive: true,
                                    scales: {
                                        x: {
                                            display: (chartKey === 'totals'),
                                        }
                                    },
                                    plugins: {
                                        legend: {
                                            display: false,
                                        },
                                        title: {
                                            display: false,
                                            text: table.title
                                        }
                                    }
                                },
                            }
                        );
                    }
                }
            }
        },
    },
    mounted: function(){
        this.get();
    }
});
