#!/bin/bash

if [[ "$*" == *"no_hls"* ]]
then
	exit 1
else
	if [[ "$*" == *"no_encode"* ]]
	then
		ARGS=( "$@" )

		for i in "${!ARGS[@]}"; do
		        case "${ARGS[i]}" in
		                '')             # Skip if element is empty (happens when it's unsetted before)
		                                continue
		                        ;;
		                -i)     input_file=${ARGS[i+1]}
                                unset 'ARGS[i+1]'
		                        ;;
		                -y)     output_file=${ARGS[i+1]}
                                unset 'ARGS[i+1]'
		                        ;;
		                --)             # End of arguments
		                                unset 'ARGS[i]'
		                                break
		                        ;;
		                *)              # Skip unset if our argument has not been matched
		                                continue
		                        ;;
		        esac
		        unset 'ARGS[i]'
		done
		ln $input_file $output_file
	else
		#if [[ "$*" == *".mp3"* ]]
		#then
		#	exit 1
		#else
			ffmpeg "$@"
		#fi
	fi
fi
