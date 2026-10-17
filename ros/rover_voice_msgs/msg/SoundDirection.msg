# The reSpeaker Flex's direction reading, about 16 times a second.

std_msgs/Header header

bool speech                # the array hears speech right now
float32 energy             # speech energy of the auto-select beam; 0 when quiet

# Direction of the speech in the rover's frame. Set only while speech is
# true and the array is calibrated.
bool has_direction
float32 direction          # radians, REP-103: 0 ahead, positive to the left

bool calibrated            # scripts/run --doa-calibrate has been run
float32 board_degrees      # raw auto-select beam angle on the board; NaN if unknown
