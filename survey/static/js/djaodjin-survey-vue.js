// components to enter survey data and display results.

var percentToggleMixin = {
    data: function() {
        var data = {
            percentToggle: 0
        }
        return data;
    },
    watch: {
        percentToggle: function(newValue, oldValue) {
            var vm = this;
            if( parseInt(newValue) > 0 ) {
                vm.params.unit = null;
            } else {
                vm.params.unit = 'percentage';
            }
        }
    }
};


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

/** Component to list, add and remove profiles that are currently invited
    to a campaign.
 */
Vue.component('engage-profiles', {
    mixins: [
        itemListMixin,
        percentToggleMixin
    ],
    data: function() {
        return {
            url: this.$urls.api_portfolios_requests,
            api_profiles_base_url: this.$urls.api_organizations,
            typeaheadUrl: this.$urls.api_account_candidates,
            params: {
                o: 'full_name'
            },
            newItem: {
                email: "",
                full_name: "",
                type: "organization",
                printable_name: "",
                created_at: null
            },
            showContacts: -1,
            showRespondents: -1,
            showRecipients: -1,
            showEditTags: -1,
            message: this.$defaultRequestInitiatedMessage,
            getCb: 'loadComplete'
        }
    },
    methods: {
        hasNoReportingStatus: function(item) {
            return (typeof item.reporting_status === 'undefined') ||
                item.reporting_status === null;
        },
        reload: function() {
            var vm = this;
            vm.lastGetParams = vm.getParams();
            var typeaheadQueryString =
                '?o=full_name&q_f=full_name&q_f=email&q=' +
                vm.lastGetParams['q'];
            vm.reqMultiple([{
                method: 'GET', url: vm.url + vm.getQueryString(),
            },{
                method: 'GET', url: vm.typeaheadUrl + typeaheadQueryString,
            }], function(resp, typeaheadResp) {
                vm.loadComplete(resp[0], typeaheadResp[0]);
            });
        },
        populateInvite: function(newAccount) {
            var vm = this;
            if( newAccount.hasOwnProperty('slug') && newAccount.slug ) {
                vm.newItem.slug = newAccount.slug;
            }
            if( newAccount.hasOwnProperty('email') && newAccount.email ) {
                vm.newItem.email = newAccount.email;
            }
            if( newAccount.hasOwnProperty('printable_name')
                && newAccount.printable_name ) {
                vm.newItem.full_name = newAccount.printable_name;
            }
            if( newAccount.hasOwnProperty('full_name')
                && newAccount.full_name ) {
                vm.newItem.full_name = newAccount.full_name;
            }
            if( newAccount.hasOwnProperty('picture')
                && newAccount.picture ) {
                vm.newItem.picture = newAccount.picture;
            }
            if( newAccount.hasOwnProperty('created_at')
                && newAccount.created_at ) {
                vm.newItem.created_at = newAccount.created_at;
            }
        },
        requestAssessment: function(campaign) {
            var vm = this;
            var data = {
                accounts: [vm.newItem],
                message: vm.message,
            }
            if( typeof campaign !== 'undefined' ) {
                data['campaign'] = campaign;
            }
            if( !vm.newItem.slug ) {
                vm.reqPost(vm.$urls.api_account_candidates, vm.newItem,
                function(resp) {
                    vm.newItem = resp;
                    data.accounts = [vm.newItem];
                    vm.reqPost(vm.$urls.api_accessibles, data,
                    function success(resp) {
                        vm.get();
                    });
                });
            } else {
                vm.reqPost(vm.$urls.api_accessibles, data,
                function success(resp) {
                    vm.get();
                });
            }
            return false;
        },
        remove: function ($event, idx) {
            var vm = this;
            vm.reqDelete(vm._safeUrl(vm.$urls.api_accessibles,
                vm.items.results[idx].slug),
            function success(resp) {
                vm.get();
            });
        },
        loadComplete: function(resp, typeaheadResp) {
            var vm = this;
            vm.items = {count: resp.count, results: []};
            if( typeof typeaheadResp === 'undefined' ) {
                typeaheadResp = {count: 0, results: []};
            }
            var leftIdx = 0, rightIdx = 0;
            for(; leftIdx < typeaheadResp.results.length &&
                rightIdx < resp.results.length ;) {
                if( typeaheadResp.results[leftIdx].printable_name
                    < resp.results[rightIdx].printable_name ) {
                    vm.items.results.push(typeaheadResp.results[leftIdx]);
                    ++leftIdx;
                } else if( typeaheadResp.results[leftIdx].printable_name
                    > resp.results[rightIdx].printable_name ) {
                    vm.items.results.push(resp.results[rightIdx]);
                    ++rightIdx;
                } else {
                    // equal? we favor resp.
                    vm.items.results.push(resp.results[rightIdx]);
                    ++leftIdx;
                    ++rightIdx;
                }
            }
            for(; leftIdx < typeaheadResp.results.length; ++leftIdx ) {
                vm.items.results.push(typeaheadResp.results[leftIdx]);
            }
            for(; rightIdx < resp.results.length; ++rightIdx ) {
                vm.items.results.push(resp.results[rightIdx]);
            }
            vm.itemsLoaded = true;
        },
        toggleContacts: function(toggledIdx) {
            var vm = this;
            var entry = vm.items.results[toggledIdx];
            vm.showContacts = vm.showContacts === toggledIdx ? -1 : toggledIdx;
            if( vm.showContacts >= 0 ) {
                const api_roles_url = vm._safeUrl(vm.api_profiles_base_url,
                    [entry.slug, 'roles']);
                vm.reqGet(api_roles_url, function(resp) {
                    entry.contacts = resp.results;
                    entry.contacts.sort(function(a, b) {
                        if( a.user.last_login ) {
                            if( b.user.last_login ) {
                                if( a.user.last_login
                                    > b.user.last_login ) {
                                    return -1;
                                }
                                if( a.user.last_login
                                    < b.user.last_login ) {
                                    return 1;
                                }
                            } else {
                                return -1;
                            }
                        } else {
                            if( b.user.last_login ) {
                                return 1;
                            } else {
                            }
                        }
                        return 0;
                    });
                    vm.$forceUpdate();
                });
            }
        },
        toggleRespondents: function(toggledIdx) {
            var vm = this;
            var entry = vm.items.results[toggledIdx];
            vm.showRespondents = vm.showRespondents === toggledIdx ? -1 : toggledIdx;
            if( vm.showRespondents >= 0 ) {
                const api_roles_url = vm._safeUrl(vm.$urls.api_sample_base_url,
                    [entry.sample, 'respondents']);
                vm.reqGet(api_roles_url, function(resp) {
                    entry.respondents = resp.results;
                    entry.respondents.sort(function(a, b) {
                        if( a.last_login ) {
                            if( b.last_login ) {
                                if( a.last_login
                                    > b.last_login ) {
                                    return -1;
                                }
                                if( a.last_login
                                    < b.last_login ) {
                                    return 1;
                                }
                            } else {
                                return -1;
                            }
                        } else {
                            if( b.last_login ) {
                                return 1;
                            } else {
                            }
                        }
                        return 0;
                    });
                    vm.$forceUpdate();
                });
            }
        },
        toggleRecipients: function(toggledIdx) {
            var vm = this;
            var entry = vm.items.results[toggledIdx];
            vm.showRecipients = vm.showRecipients === toggledIdx ? -1 : toggledIdx;
            if( vm.showRecipients >= 0 ) {
                const api_roles_url = vm._safeUrl(vm.$urls.api_activities_base,
                    [entry.slug, 'recipients']);
                vm.reqGet(api_roles_url, function(resp) {
                    entry.recipients = resp.results;
                    entry.recipients.sort(function(a, b) {
                        if( a.user.last_login ) {
                            if( b.user.last_login ) {
                                if( a.user.last_login
                                    > b.user.last_login ) {
                                    return -1;
                                }
                                if( a.user.last_login
                                    < b.user.last_login ) {
                                    return 1;
                                }
                            } else {
                                return -1;
                            }
                        } else {
                            if( b.user.last_login ) {
                                return 1;
                            } else {
                            }
                        }
                        return 0;
                    });
                    vm.$forceUpdate();
                });
            }
        },
        saveTags: function(item) {
            var vm = this;
            if( !item.extra ) {
                item.extra = {}
            }
            item.extra.tags = item.tagsAsText.split(',');
            vm.reqPatch(vm._safeUrl(vm.$urls.api_accessibles, [
                'metadata', item.slug]), {extra: {tags: item.extra.tags}});
            vm.showEditTags = -1;
        },
        toggleEditTags: function(toggledIdx) {
            var vm = this;
            var entry = vm.items.results[toggledIdx];
            vm.showEditTags = vm.showEditTags === toggledIdx ? -1 : toggledIdx;
            if( vm.showEditTags >= 0 ) {
                if( !entry.tagsAsText ) {
                    try {
                        entry.tagsAsText = entry.extra.tags.join(", ");
                    } catch (err) {
                        entry.tagsAsText = "";
                    }
                }
            }
        }
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
      minChars: 3,
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
