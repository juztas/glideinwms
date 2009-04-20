#
#
# Description:
#  This module implements plugins for the VO frontend
#
# Author:
#  Igor Sfiligoi  (since Mar 31st 2009)
#

import os,os.path,time
import sets
import pickle
import glideinFrontendLib


################################################################################
#                                                                              #
####    Proxy plugins                                                       ####
#                                                                              #
# All plugins implement the following interface:                               #
#   __init_(config_dir,proxy_list)                                             #
#     Constructor, config_dir may be used for internal config/cache files      #
#   get_required_job_attributes()                                              #
#     Return the list of required condor_q attributes                          #
#   get_required_classad_attributes()                                          #
#     Return the list of required condor_status attributes                     #
#   get_proxies(condorq_dict,condorq_dict_types,status_dict,status_dict_types) #
#     Return a list of proxies that match the input criteria                   #
#     Each element is a (index, value) pair                                    #
#     If called multiple time, it is guaranteed that                           #
#        if the index is the same, the proxy is (logicaly) the same            #
#                                                                              #
################################################################################

############################################
#
# This plugin always returns the first proxy
# Useful when there is only one proxy
# or for testing
#
class ProxyFirst:
    def __init__(self,config_dir,proxy_list):
        self.proxy_list=list2ilist(proxy_list)

    # what job attributes are used by this plugin
    def get_required_job_attributes(self):
        return []

    # what glidein attributes are used by this plugin
    def get_required_classad_attributes(self):
        return []

    # get the proxies, given the condor_q and condor_status data
    def get_proxies(condorq_dict,condorq_dict_types,
                    status_dict,status_dict_types):
        return [self.proxy_list[0]]

############################################
#
# This plugin returns all the proxies
# This is can be a very useful default policy
#
class ProxyAll:
    def __init__(self,config_dir,proxy_list):
        self.proxy_list=list2ilist(proxy_list)

    # what job attributes are used by this plugin
    def get_required_job_attributes(self):
        return []

    # what glidein attributes are used by this plugin
    def get_required_classad_attributes(self):
        return []

    # get the proxies, given the condor_q and condor_status data
    def get_proxies(condorq_dict,condorq_dict_types,
                    status_dict,status_dict_types):
        return self.proxy_list

##########################################################
#
# This plugin uses the first N proxies
# where N is the number of users currently in the system
#
# This is useful if the first proxies are higher priority
# then the later ones
# Also good for testing
#
class ProxyUserCardinality:
    def __init__(self,config_dir,proxy_list):
        self.proxy_list=list2ilist(proxy_list)

    # what job attributes are used by this plugin
    def get_required_job_attributes(self):
        return ('User',)

    # what glidein attributes are used by this plugin
    def get_required_classad_attributes(self):
        return []

    # get the proxies, given the condor_q and condor_status data
    def get_proxies(condorq_dict,condorq_dict_types,
                    status_dict,status_dict_types):
        users_set=glideinFrontendLib.getCondorQUsers(condorq_dict)
        return self.get_proxies_from_cardinality(len(users_set))

    #############################
    # INTERNAL
    #############################

    # return the proxies based on data held by the class
    def get_proxies_from_cardinality(self,nr_requested_proxies):
        nr_proxies=len(self.proxy_list)

        if nr_requested_proxies>=nr_proxies:
            # wants all of them, no need to select
            return self.proxy_list
        
        out_proxies=[]
        for i in range(nr_requested_proxies):
            out_proxies.append(self.proxy_list[i])

        return out_proxies

######################################################################
#
# This plugin implements a user-based round-robin policy
# The same proxies are used as long as the users don't change
#  (we keep a disk-based memory for this purpose)
# Once any user leaves, the most used proxy is returned to the pool
# If a new user joins, the least used proxy is obtained from the pool
#
class ProxyUserRR:
    def __init__(self,config_dir,proxy_list):
        self.proxy_list=list2ilist(proxy_list)
        self.config_dir=config_dir
        self.config_fname="%s/proxy_user_rr.dat"%self.config_dir
        self.load()

    # what job attributes are used by this plugin
    def get_required_job_attributes(self):
        return ('User',)

    # what glidein attributes are used by this plugin
    def get_required_classad_attributes(self):
        return []

    # get the proxies, given the condor_q and condor_status data
    def get_proxies(condorq_dict,condorq_dict_types,
                    status_dict,status_dict_types):
        new_users_set=glideinFrontendLib.getCondorQUsers(condorq_dict)
        old_users_set=self.config_data['users_set']
        if old_users_set==new_users_set:
            return self.get_proxies_from_data()

        # users changed
        removed_users=old_users_set-new_users_set
        added_users=new_users_set-old_users_set

        if len(removed_users)>0:
            self.shrink_proxies(len(removed_users))
        if len(added_users)>0:
            self.expand_proxies(len(added_users))

        self.config_data['users_set']=new_users_set
        self.save()

        return self.get_proxies_from_data()

    #############################
    # INTERNAL
    #############################

    # load from self.config_fname into self.config_data
    # if the file does not exist, create a new config_data
    def load(self):
        if os.path.isfile(self.config_fname):
            fd=open(self.config_fname,"r")
            try:
                self.config_data=pickle.load(fd)
            finally:
                fd.close()
            #
            # NOTE: This will not work if proxies change between reconfigs :(
            #
        else:
            self.config_data={'users_set':sets.Set(),
                              'proxies_range':{'min':0,'max':0}}

        return

    # save self.config_data into self.config_fname
    def save(self):
        # fist save in a tmpfile
        tmpname="%s~"%self.config_fname
        try:
            os.unlink(tmpname)
        except:
            pass # just trying
        fd=open(tmpname,"w")
        try:
            pickle.dump(self.config_data,fd,0) # use ASCII version of protocol
        finally:
            fd.close()

        # then atomicly move it in place
        os.rename(tmpname,self.config_fname)

        return

    # remove a number of proxies from the internal data
    def shrink_proxies(self,nr):
        min_proxy_range=self.config_data['proxies_range']['min']
        max_proxy_range=self.config_data['proxies_range']['max']

        min_proxy_range+=nr
        if min_proxy_range>max_proxy_range:
            raise RuntimeError,"Cannot shrink so much: %i requested, %i available"%(nr, max_proxy_range-self.config_data['proxies_range']['min'])
        
        self.config_data['proxies_range']['min']=min_proxy_range

        return

    # add a number of proxies from the internal data
    def expand_proxies(self,nr):
        min_proxy_range=self.config_data['proxies_range']['min']
        max_proxy_range=self.config_data['proxies_range']['max']

        max_proxy_range+=nr
        if min_proxy_range>max_proxy_range:
            raise RuntimeError,"Did we hit wraparound after the requested exansion of %i? min %i> max %i"%(nr, min_proxy_range,max_proxy_range)

        self.config_data['proxies_range']['max']=max_proxy_range

        return

    # return the proxies based on data held by the class
    def get_proxies_from_data(self):
        nr_proxies=len(self.proxy_list)

        min_proxy_range=self.config_data['proxies_range']['min']
        max_proxy_range=self.config_data['proxies_range']['max']
        nr_requested_proxies=max_proxy_range-min_proxy_range;

        if nr_requested_proxies>=nr_proxies:
            # wants all of them, no need to select
            return self.proxy_list
        
        out_proxies=[]
        for i in range(min_proxy_range,max_proxy_range):
            real_i=i%nr_proxies
            out_proxies.append(self.proxy_list[i])

        return out_proxies

######################################################################
#
# This plugin implements a user-based mapping policy
#  with possibility of recycling of accounts:
#  * when a user first enters the system, it gets mapped to a
#    pilot proxy that was not used for the longest time
#  * for existing users, just use the existing mapping
#  * if an old user comes back, it may be mapped to the old account, if not
#    yet recycled, else it is treated as a new user
#
class ProxyUserMapWRecycling:
    def __init__(self,config_dir,proxy_list):
        self.proxy_list=proxy_list
        self.config_dir=config_dir
        self.config_fname="%s/proxy_usermap_wr.dat"%self.config_dir
        self.load()

    # what job attributes are used by this plugin
    def get_required_job_attributes(self):
        return ('User',)

    # what glidein attributes are used by this plugin
    def get_required_classad_attributes(self):
        return []

    # get the proxies, given the condor_q and condor_status data
    def get_proxies(condorq_dict,condorq_dict_types,
                    status_dict,status_dict_types):
        users=tuple(glideinFrontendLib.getCondorQUsers(condorq_dict))
        out_proxies=[]

        user_map=self.config_data['user_map']

        for user in users:
            if not user_maps.has_key(user):
                # user not in cache, get the oldest unused entry
                # not ordered, need to loop over the whole cache
                min_key=0 # will compare all others to the first
                keys=user_map.keys()[1:]
                for k in keys:
                    if user_map[k]['last_seen']<user_map[min_key]['last_seen']:
                        min_key=k

                # replace min_key with the current user
                user_map[user]=user_map[min_key]
                del user_map[min_key]
            # else the user is already in the cache... just use that
            
            cel=user_map[user]
            out_proxies.append((cel['proxy_index'],cel['proxy']))
            # save that you have indeed seen the user 
            cel['last_seen']=time.time()

        # save changes
        self.save()

        return out_proxies

    #############################
    # INTERNAL
    #############################

    # load from self.config_fname into self.config_data
    # if the file does not exist, create a new config_data
    def load(self):
        if not os.path.exist(self.config_fname):
            # no cache, create new cache structure from scratch
            self.config_data={}
            user_map={}
            nr_proxies=len(self.proxy_list)
            for i in range(nr_proxies):
                # use numbers for keys, so we are user will not mutch to any user string
                user_map[i]={'proxy':self.proxy_list[i],
                             'proxy_index':i,
                             'last_seen':0} #0 is the oldest UNIX have ever seen ;)
            self.config_data['user_map']=user_map
            self.config_data['first_free_index']=nr_proxies # this will be used for future updates
        else:
            # load cache
            fd=open(self.config_fname,"r")
            try:
                self.config_data=pickle.load(fd)
            finally:
                fd.close()

            # if proxies changed, remove old ones and insert the new ones
            new_proxies=sets.Set(self.proxy_list)
            cached_proxies=sets.Set() # here we will store the list of proxies in the cache

            user_map=self.config_data['user_map']
            
            # need to iterate, since not indexed by proxy name
            keys=user_map.keys()
            for k in keys:
                el=user_map[k]
                el_proxy=el['proxy']
                if not (el_proxy in new_proxies):
                    # cached proxy not used anymore... remove from cache
                    del user_map[k]
                else:
                    # add to the list, will process later
                    cached_proxies.add(el_proxy)

            added_proxies=new_proxies-cached_proxies
            # now that we know what proxies have been added, put them in cache
            for proxy in added_proxies:
                idx=self.config_data['first_free_index']
                # use numbers for keys, so we are user will not mutch to any user string
                user_map[idx]={'proxy':proxy,
                               'proxy_index':idx,
                               'last_seen':0} #0 is the oldest UNIX have ever seen ;)
                self.config_data['first_free_index']=idx+1            

        return

    # save self.config_data into self.config_fname
    def save(self):
        # fist save in a tmpfile
        tmpname="%s~"%self.config_fname
        try:
            os.unlink(tmpname)
        except:
            pass # just trying
        fd=open(tmpname,"w")
        try:
            pickle.dump(self.config_data,fd,0) # use ASCII version of protocol
        finally:
            fd.close()

        # then atomicly move it in place
        os.rename(tmpname,self.config_fname)

        return

###############################################
# INTERNAL to proxy_plugins, don't use directly

# convert a list into a list of (index, value)

#
# NOTE: This will not work if proxy order is changed between reconfigs :(
#

def list2ilist(lst):
    out=[]
    for i in range(length(lst)):
        out.append((i,lst[i]))
    return out


    
###################################################################

# Being plugins, users are not expected to directly reference the classes
# They should go throug the dictionaries below to find the appropriate plugin

proxy_plugins={'ProxyAll':ProxyAll,
               'ProxyUserRR':ProxyUserRR,
               'ProxyFirst':ProxyFirst,
               'ProxyUserCardinality':ProxyUserCardinality,
               'ProxyUserMapWRecycling':ProxyUserMapWRecycling}

