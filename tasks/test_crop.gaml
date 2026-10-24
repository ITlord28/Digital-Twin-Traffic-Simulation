model TestCropRoadShp

global {
    file road_shp <- shape_file("../1_Digital_Twin_Vehicle_Detection/gama_vehicle_twin/includes/road 4.shp");
    point center_pt <- {583815.0, -1107780.0};
    geometry crop_box <- rectangle({300.0, 300.0}) at_location center_pt;
    
    init {
        create road from: road_shp where (each.shape intersects crop_box);
        write "Number of roads in cropped intersection: " + length(road);
        loop r over: road {
            write "Road shape: " + r.shape + " lanes=" + r.lanes + " width=" + r.width;
        }
        write "Cropped envelope: " + envelope(road);
    }
}

species road {
    int lanes;
    float width;
}

experiment TestExp type: gui {}
