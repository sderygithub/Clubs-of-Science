import datetime

#datestr = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S").replace(' ','_')
datestr = ''
outputfolder = '/Users/sdery/Development/Website/Flask/static/maps/richclubs/'
seedtopic = 'neuroscience'
journals = ['proceedings of the national academy of sciences',
            'science',
            'nature'
            'neuroscience',
            'neuroimaging',
            'neuron',
            'cortical']

"""
seedtopic = 'neuroimaging'
journals = ['journal of nanoparticle research',
            'proceedings of the national academy of sciences',
            'science',
            'nature'
            'the journal of physical chemistry',
            'nanotechnology',
            'biotech',
            'drug discovery',
            'biomaterials']
            
#seedtopic = 'nanotechnology'
#seedtopic = 'epidemiology'
#seedtopic = 'machine_learning'
#seedtopic = 'data_science'



journals = ['proceedings of the national academy of sciences',
            'science',
            'nature',
            'epidemiology',
            'network',
            'disease']

journals = ['neural',
            'algorithm',
            'networks',
            'classification',
            'statistical',
            'regression',
            'optimization']

journals = ['science',
            'nature',
            'learning',
            'statistical']
"""
"""
index = 1
loop_escape = 0
author_dict = {}
authors_id = []
result = _get_authors_from_label(seedtopic,'')
authors_id = authors_id + result['authors_id'];
for iter in range(19):
  result = _get_authors_from_label(seedtopic,result['after_author'])
  authors_id = authors_id + result['authors_id'];
authors_list = unique(authors_id)
"""
# Additive steps
num_profile_to_visit_steps = [100,150,250,500,500,1000]
num_profile_to_visit_steps = [183,500,500,500,500]
for num_profile_to_visit in num_profile_to_visit_steps:
	
	print 'Acquiring data...'
	execfile('cos-demo.py')

	print 'Building graph...'
	execfile('cos-analysis.py')
	outputfile = outputfolder + 'journal_graph_' + seedtopic + '_' + str(index) + '.json'
	json.dump(d3map, open(outputfile, 'w'), indent=2)

	print 'Word frequency computation...'
	execfile('cos-wordstudy.py')
	outputfile = outputfolder + 'journal_words_' + seedtopic + '_' + str(index) + '.json'
	json.dump(group_mostfrequentword, open(outputfile, 'w'), indent=2)
