// components to enter survey data and display results.

(function (root, factory) {
    if (typeof define === 'function' && define.amd) {
        // AMD. Register as an anonymous module.
        define(['exports', 'jQuery'], factory);
    } else if (typeof exports === 'object' && typeof exports.nodeName !== 'string') {
        // CommonJS
        factory(exports, require('jQuery'));
    } else {
        // Browser true globals added to `window`.
        factory(root, root.jQuery);
        // If we want to put the exports in a namespace, use the following line
        // instead.
        // factory((root.djResources = {}), root.jQuery);
    }
}(typeof self !== 'undefined' ? self : this, function (exports, jQuery) {

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


Vue.component('compare-samples', {
    mixins: [
        itemListMixin
    ],
    data: function() {
        return {
            url: this.$urls.survey_api_compare_samples,
            params: {
                o: '-created_at'
            },
            newItem: {
                title: ''
            }
        }
    },
    methods: {
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
        itemListMixin,
        accountDetailMixin
    ],
    props: {
        defaultSelectedAccounts: {
            type: Array,
            default: function() {
                return [];
            }
        },
        defaultSelectedCampaign: {
            type: Object,
            default: function() {
                return null;
            }
        },
        defaultGrantCandidates: {
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
                campaign: null,
                message: "",
                accounts: [],
            },
            getCompleteCb: 'getCompleted',
            profileRequestDone: false
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
            vm.grant.grantee = newGrantee;
            vm.populateAccounts([vm.grant.grantee]);
            if( newGrantee.slug ) {
                vm.profileRequestDone = false;
            } else {
                vm.profileRequestDone = true;
                if( vm.$refs.fullName ) {
                    vm.$nextTick(function() {
                        vm.$refs.fullName.focus();
                    });
                }
            }
            return false;
        },
        _preparePortfolios: function(grant) {
            var vm = this;
            var portfolios = {};
            portfolios.grantee = {
                email: vm.getAccountField(grant.grantee, 'email'),
                full_name: vm.getAccountField(grant.grantee, 'full_name') ||
                    vm.getAccountField(grant.grantee, 'printable_name')
            };
            if( grant.campaign ) {
                portfolios.campaign = grant.campaign.slug || grant.campaign;
            }
            if( grant.grantee.slug ) {
                portfolios.grantee.slug = grant.grantee.slug;
            }
            if( grant.grantee.message ) {
                portfolios.message = grant.grantee.message;
            } else if( grant.message ) {
                portfolios.message = grant.message;
            }
            if( grant.accounts.length > 0 ) {
                portfolios.accounts = [];
                for( var idx = 0; idx < grant.accounts.length; ++idx ) {
                    portfolios.accounts.push(grant.accounts[idx].slug);
                }
            }
            return portfolios;
        },
        submitPortfolios: function(portfolios) {
            var vm = this;
            vm.reqPost(vm.url, portfolios,
            function(resp) { // success
                vm.reload();
                vm.grant.grantee = {email: ""};
            });
        },
        submitGrants: function() {
            var vm = this;
            if( vm.grant.grantee.slug || vm.grant.grantee.email) {
                vm.profileRequestDone = false;
                var portfolios = vm._preparePortfolios(vm.grant);
                if( portfolios.grantee.slug ) {
                    vm.submitPortfolios(portfolios);
                } else {
                    vm.reqPost(vm.url_account_base, portfolios.grantee,
                    function(resp) {
                        var email = portfolios.grantee.email;
                        portfolios.grantee = resp;
                        portfolios.grantee.email = email;
                        vm.submitPortfolios(portfolios);
                    });
                }
            } else {
                vm.profileRequestDone = true;
                if( vm.$refs.typeahead && vm.$refs.typeahead.query ) {
                    vm.grant.grantee.email = vm.$refs.typeahead.query;
                    if( vm.$refs.fullName ) {
                        vm.$nextTick(function() {
                            vm.$refs.fullName.focus();
                        });
                    }
                }
            }
        },
        ignore: function(portfolio, idx) {
            var vm = this;
            vm.reqDelete(portfolio.api_remove,
            function(resp) { // success
                vm.items.results.splice(idx, 1);
            });
        },
        getCompleted: function(){
            var vm = this;
            vm.populateAccounts(vm.items.results, 'grantee');
            vm.populateAccounts(vm.items.results, 'account');
        },
    },
    computed: {
        grantCandidates: function() {
            var vm = this;
            var results = [];
            if( vm.itemsLoaded && vm.items.results ) {
                for( var idx = 0;
                     idx < vm.defaultGrantCandidates.length; ++idx ) {
                    var found = false;
                    for( var jdx = 0; jdx < vm.items.results.length; ++jdx ) {
                        if( vm.items.results[jdx].grantee
                            == vm.defaultGrantCandidates[idx].grantee ) {
                            found = true;
                            break
                        }
                    }
                    if( !found ) {
                        results.push(vm.defaultGrantCandidates[idx]);
                    }
                }
            }
            return results;
        },
        showAccounts: function() {
            return this.grant.grantee.slug || this.grant.grantee.email;
        }
    },
    mounted: function(){
        var vm = this;
        vm.get();
        if( vm.defaultSelectedAccounts ) {
            vm.grant.accounts = vm.defaultSelectedAccounts;
            vm.populateAccounts(vm.grant.accounts);
        }
        if( vm.defaultSelectedCampaign ) {
            vm.grant.campaign = vm.defaultSelectedCampaign;
        }
        if( vm.$refs.message ) {
            vm.grant.message = vm.$refs.message.textContent;
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

// Vue components to select accounts in compare queries
// ----------------------------------------------------
Vue.component('query-individual-account', {
    mixins: [
        itemMixin
    ],
    props: [
        'disabled',
        'period',
        'prefix'
    ],
    data: function() {
        return {
            account: null,
            samples: [],
            selectedSample: -1,
            params: {
                start_at: null,
                ends_at: null,
                period_type: null
            },
            humanizeDate: function(at_time) {
                return at_time.toString();
            }
        }
    },
    methods: {
        validate: function() {
            var vm = this;
            vm.samples[vm.selectedSample].title = vm.account.printable_name + "- " + vm.samples[vm.selectedSample].title;
            vm.$emit('updatedataset', vm.samples[vm.selectedSample]);
            vm.account = null;
            vm.samples = [];
            vm.selectedSample = -1;
            vm.$refs.account.reset();
        },
        selectAccount: function(dataset, newAccount) {
            var vm = this;
            vm.account = newAccount;
            vm.reqGet(vm._safeUrl(
                vm.$urls.api_version + '/' + vm.account.slug, 'sample'),
            function (resp) {
                for( let idx = 0; idx < resp.results.length; ++idx ) {
                    if( resp.results[idx].is_frozen ) {
                        const title = vm.humanizeDate(resp.results[idx].created_at) + (resp.results[idx].verified_status !== 'no-review' ? " - Verified" : "" );
                        const url = vm._safeUrl(vm._safeUrl(
                            vm.$urls.api_version + '/' + vm.account.slug + '/sample/' + resp.results[idx].slug, 'content'), vm.prefix);
                        var data = resp.results[idx];
                        data.title = title;
                        data.url = url;
                        vm.samples.push(data);
                    }
                }
            });
        }
    },
    computed: {
        hasAccount: function() {
            return this.account;
        },
        hasSamples: function() {
            return this.samples != null && this.samples.length > 0;
        }
    },
    mounted: function(){
        if( this.$el.dataset && this.$el.dataset.humanizeDate ) {
            this.humanizeDate = eval(this.$el.dataset.humanizeDate);
        }
    }
});


Vue.component('query-group-accounts', {
    mixins: [
        itemListMixin
    ],
    props: [
        'disabled',
        'period',
        'prefix'
    ],
    data: function() {
        return {
            url: this.$urls.api_account_groups,
            newItem: {title: ""},
            selectedItem: -1,
            addAccountEnabled: false,
            params: {
                start_at: null,
                ends_at: null,
                period_type: null
            }
        }
    },
    methods: {
        addAccount: function(dataset, newAccount) {
            var vm = this;
            newAccount['full_name'] = newAccount.printable_name;
            var group = vm.items.results[vm.selectedItem];
            vm.reqPost(vm._safeUrl(vm.url, group.slug), newAccount,
            function(resp) {
                if(typeof group.accounts === 'undefined' ) {
                    group.accounts = [];
                }
                group.accounts.push(resp);
                vm.addAccountEnabled = false;
                vm.$refs.account.reset();
            });
        },
        addItem: function() {
            var vm = this;
            vm.reqPost(vm.url, vm.newItem, function(resp) {
                const oldSelectedItem = vm.selectedItem;
                vm.selectedItem = vm.items.results.length;
                vm.items.results.push(resp);
                vm.loadAccounts(oldSelectedItem, vm.selectedItem);
            });
        },
        getAccounts: function(group) {
            if( group && typeof group.accounts != 'undefined' ) {
                return group.accounts;
            }
            return [];
        },
        loadAccounts: function() {
            var vm = this;
            if( vm.selectedItem >= 0 ) {
                var group = vm.items.results[vm.selectedItem];
                vm.reqGet(vm._safeUrl(vm.url, group.slug), function(resp) {
                    vm.items.results[vm.selectedItem].accounts = resp.results;
                    vm.$forceUpdate();
                });
            }
        },
        removeAccount: function(idx) {
            var vm = this;
            var group = vm.items.results[vm.selectedItem];
            vm.reqDelete(vm._safeUrl(vm._safeUrl(vm.url, group.slug), idx));
        },

        accountsLoaded: function() {
            const vm = this;
            if( vm.selectedItem >= 0 ) {
                return vm.items.results[vm.selectedItem].hasOwnProperty('accounts');
            }
            return false;
        },
        accountsEmpty: function() {
            const vm = this;
            if( vm.accountsLoaded() ) {
                return vm.items.results[vm.selectedItem].accounts.length === 0;
            }
            return true;
        },
        validate: function() {
            var vm = this;
            const group = vm.items.results[vm.selectedItem];
            const title = group.title;
            const url = vm._safeUrl(vm._safeUrl(
                vm.$urls.api_benchmarks_index, group.slug),
                vm.prefix) + vm.getQueryString();
            const dataset = {title: title, url: url};
            vm.$emit('updatedataset', dataset);
            vm.$refs.account.reset();
        },
    },
    mounted: function() {
        this.get();
    }
});


var QueryAccountsByAffinity = Vue.component('query-accounts-by-affinity', {
    mixins: [
        itemMixin
    ],
    props: [
        'disabled',
        'period',
        'prefix'
    ],
    data: function() {
        return {
            affinityType: "all",
            params: {
                start_at: null,
                ends_at: null,
                period_type: null
            }
        }
    },
    methods: {
        _getAffinityBaseDataset: function(affinityType) {
            var vm = this;
            if( !affinityType ) {
                affinityType = vm.affinityType;
            }
            vm.params.period_type = vm.period ? vm.period : null;
            const title = vm.$el.querySelector(
                '[value="' + affinityType + '"]').textContent;
            const url = vm._safeUrl(vm._safeUrl(
                vm.$urls.api_benchmarks_index, affinityType),
                vm.prefix) + vm.getQueryString();
            return {title: title, url: url};
        },
        validate: function() {
            var vm = this;
            const dataset = vm._getAffinityBaseDataset();
            vm.$emit('updatedataset', dataset);
        },
    },
});


var QueryAccountsByAnswers = Vue.component('query-accounts-by-answers', {
    mixins: [
        itemListMixin
    ],
    props: [
        'disabled',
        'period',
        'prefix'
    ],
    data: function() {
        return {
            url: this.$urls.api_account_groups,
            newItem: {
                'title': "",
            },
            newPredicate: {
                'question': null,
                'measured': null
            },
            selectedItem: -1,
            addPredicateEnabled: false,
            questions: [],
            params: {
                start_at: null,
                ends_at: null,
                period_type: null
            },
            cachedUnits: {}
        }
    },
    methods: {
        addItem: function() {
            var vm = this;
            vm.reqPost(vm.url, vm.newItem, function(resp) {
                const oldSelectedItem = vm.selectedItem;
                vm.selectedItem = vm.items.results.length;
                vm.items.results.push(resp);
                vm.loadPredicates(oldSelectedItem, vm.selectedItem);
            });
        },
        addPredicate: function() {
            var vm = this;
            var group = vm.items.results[vm.selectedItem];
            const data = {
                'path': vm.newPredicate.question.path,
                'measured': vm.newPredicate.measured,
            };
            vm.reqPost(vm._safeUrl(vm.url, group.slug), data,
            function(resp) {
                if(typeof group.predicates === 'undefined' ) {
                    group.predicates = [];
                }
                group.predicates.push(resp);
                vm.addPredicateEnabled = false;
                vm.newPredicate = {
                    'question': null,
                    'measured': null
                };
            });
        },
        getChoices: function(question) {
            const vm = this;
            const unit = question ? vm.cachedUnits[question.default_unit.slug] : null;
            return unit ? unit.choices : [];
        },
        getPredicates: function(group) {
            if( group && typeof group.predicates != 'undefined' ) {
                return group.predicates;
            }
            return [];
        },
        loadPredicates: function() {
            var vm = this;
            if( vm.selectedItem >= 0 ) {
                var group = vm.items.results[vm.selectedItem];
                vm.reqGet(vm._safeUrl(vm.url, group.slug), function(resp) {
                    vm.items.results[vm.selectedItem].predicates = resp.accounts_by;
                    vm.addPredicateEnabled = (
                      vm.items.results[vm.selectedItem].predicates.length == 0);
                    vm.$forceUpdate();
                });
            }
        },
        predicatesLoaded: function() {
            const vm = this;
            if( vm.selectedItem >= 0 ) {
                return vm.items.results[vm.selectedItem].hasOwnProperty('predicates');
            }
            return false;
        },
        predicatesEmpty: function() {
            const vm = this;
            if( vm.predicatesLoaded() ) {
                return vm.items.results[vm.selectedItem].predicates.length === 0;
            }
            return true;
        },
        selectQuestion: function(dataset, question) {
            var vm = this;
            vm.newPredicate.question = question;
            if( !vm.unitDetailsLoaded(question) ) {
                vm.reqGet(vm._safeUrl(
                    vm.$urls.api_units, question.default_unit.slug),
                function (resp) {
                    vm.cachedUnits[resp.slug] = resp;
                    vm.$forceUpdate();
                });
            }
        },
        unitDetailsLoaded: function(question) {
            const vm = this;
            return question && vm.cachedUnits.hasOwnProperty(question.default_unit.slug);
        },
        validate: function() {
            var vm = this;
            const group = vm.items.results[vm.selectedItem];
            const title = group.title;
            const url = vm._safeUrl(vm._safeUrl(
                vm.$urls.api_benchmarks_index, group.slug
            ), vm.prefix) + vm.getQueryString();
            const dataset = {title: title, url: url};
            vm.$emit('updatedataset', dataset);
        },
    },
    computed: {
        hasQuestion: function() {
            return this.newPredicate.question;
        },
        hasQuestions: function() {
            return this.questions && this.questions.length > 0;
        }
    },
    mounted: function() {
        var vm = this;
        vm.get();
//XXX        vm.reqGet(vm.$urls.api_campaign_questions, function(resp) {
//            vm.questions = resp.results;
//        });
    }
});


// Generic typeahead widgets
var AccountTypeAhead = Vue.component('account-typeahead', {
    mixins: [
        typeAheadMixin
    ],
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
                  if( vm.items.length === 1 ) {
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
            vm.clear();
            if( typeof newItem.printable_name !== 'undefined' ) {
                vm.query = newItem.printable_name;
            }
            vm.$emit('selectitem', vm.dataset, newItem);
            // XXX We are letting the parent decide to do reset or not
            // vm.reset();
        }
    }
});


Vue.component('grantee-typeahead', AccountTypeAhead.extend({
  data: function data() {
    return {
      url: this.$urls.api_account_candidates,
      items: [],
      query: '',
      current: -1,
      loading: false,
      selectFirst: false,
      minChars: 3,
      queryParamName: 'q',
    };
  },
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


Vue.component('campaign-typeahead', {
  mixins: [
      typeAheadMixin
  ],
  props: ['dataset'],
  data: function data() {
    return {
      url: this.$urls.api_campaign_typeahead,
      items: [],
      query: '',
      current: -1,
      loading: false,
      selectFirst: false,
      queryParamName: 'q'
    };
  },
  methods: {
    setActiveAndHit: function(item) {
      var vm = this;
      vm.setActive(item);
      vm.hit();
    },
    onHit: function(newItem) {
      var vm = this;
      if( newItem.title ) {
        vm.$emit('selectitem', vm.dataset, newItem);
        vm.query = newItem.title;
      }
      vm.clear();
    },
  }
});


QuestionTypeahead = Vue.component('question-typeahead', {
  mixins: [
      typeAheadMixin
  ],
  props: ['dataset'],
  data: function data() {
    return {
      url: this.$urls.api_question_typeahead,
      items: [],
      query: '',
      current: -1,
      loading: false,
      selectFirst: false,
      queryParamName: 'q',
      filterCampaign: null
    };
  },
  methods: {
    setActiveAndHit: function(item) {
      var vm = this;
      vm.setActive(item);
      vm.hit();
    },
    onHit: function(newItem) {
      var vm = this;
      if( newItem.title ) {
        vm.$emit('selectitem', vm.dataset, newItem);
        vm.query = newItem.title;
      }
      vm.clear();
    },
    selectCampaign: function(dataset, campaign) {
        var vm = this;
        vm.filterCampaign = campaign;
        vm.url = vm._safeUrl(this.$urls.api_question_typeahead, campaign.slug);
    },
  }
});


Vue.component('default-unit-typeahead', {
    mixins: [
        typeAheadMixin
    ],
    props: [
        'question'
    ],
    data: function data() {
        return {
            url: this.$urls.api_units,
        };
    },
    methods: {
        onHit: function onHit(newItem) {
            var vm = this;
            if( newItem.title ) {
                vm.query = newItem.title;
            }
            vm.$emit('selectitem', newItem, vm.question);
        }
    },
    mounted: function() {
        var vm = this;
        if( vm.question && vm.question.default_unit ) {
            vm.query = vm.question.default_unit.slug;
        }
    }
});

    exports.QueryAccountsByAffinity = QueryAccountsByAffinity;
    exports.QueryAccountsByAnswers = QueryAccountsByAnswers;
}));
