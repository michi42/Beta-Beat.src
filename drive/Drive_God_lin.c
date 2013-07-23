/* Parallelised version of Drive_God_lin.c of 15/05/2011 using Openmp.
   NB this version uses as the number of turns the minimum of the number
   actually read or the number given in the DrivingTerms file.

   Version <x3> 20121106 (tbach)
   - removed all (?) unused code
   - changed options reading to allow trailing spaces
   - introduced more options and more columns in output for natural tune
   - cleaned source code

   Version <x2> 20121031 (rwasef/tbach)
   - introduced more columns in output, increased variable size for this (rwasef)
   - removed iformat variable and not used code
   - rewritten option file parsing, order is not important anymore
   - removed all unused variables

   Version <x> 20121001 (tbach):
   - fixed comment line reading (by rtomas)
   - changed variable names to more meaningful and readable names
   - fixed errors from static code analysis
   - removed outcommented code
   - removed unused variables and functions
   - formatted the source
   - changed error messages to more helpful content for the user

   Change 10/08/2012 increase size of character strings
   dataFilePath[500], noisefile[500] from 300 to 500. Long datafile name was causing
   a segv when it was being read.
   Increased size of maxturns define to handle more turns.
   Fortran sourcecode changed, too.

   Change 29/03/2012 at line 43: remove window variables from the
   threadprivate pragma. These are global constants which were undefined
   other than in the primary thread so noise1, co and co2 were being
   calculated as zero in all secondary threads.

   Change 29/09/2011 at lines 715 and 724 to find lines with any
   bpm name to sort in order by looking for a " rather than a name string.
   Has matching sussix4drivexxNoO.f      H.Renshall & E.Maclean
   
   Change 22/07/2013: -Certain local main variables grouped in a struct called 'Data'
   -Removed any rejections in BPMstatus function
   -Changed formatLinFile to be OS compatible, makefile also modified, drive can now 
   be compiled using 'make' on both linux and windows
   -In general, the makefile and code only distinguish between windows and non-windows 
   with the hopes that other OS's will work with the linux version.  If this turns out 
   to not be the case, the code can easily be modified to allow for another OS.
   -Removed some unused and unnecessary code     A. Sherman
   */

#include <sys/types.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <omp.h>
#include <ctype.h>
#define MAXPICK 1100
#define MAXTURNS 10000 /* Critical parameter in sussixfordiveNoO.f, same parameter name !*/
#define MAXTURNS4 40000 /*Always four times  MAXTURNS*/
#define MAXRUNS 100
#define NATTUNE_DEFAULT -100

#if !defined(LOG_INFO)
#define LOG_INFO 0 /*set to 1 to enable log prints (tbach) */
#endif

int readDrivingTerms(FILE*, int*, char*, const int);
int getNextInt(FILE*);
void writeSussixInput(const char*, const int, const double, const double, const double);
int BPMstatus(const int, const int);
int containsChar(const char*, const char);
int containsString(const char*, const char*);
int canOpenFile(const char*);
void assertSmaller(const int, const int, const char*);
void setPath(char*, const size_t, const char*, const char*, const char*);
FILE* getFileToWrite(const char*);
FILE* getFileToRead(const char*);
FILE* __getFileWithMode(const char*, const char*, const char*);
void printTuneValue(FILE*, const char*, const int, const double, const double);
void formatLinFile(const char*, const int, const double, const double, const char*, const int, const double, const double, const char*);

/*Determines if OS is windows or not and declares external fortran function.
Linux and windows have different requirements for names of subroutines in fortran called from C. 
Code works on assumption that other operating systems will work with the linux version, but if this 
is not the case then it is easy to add another OS to be used*/
#ifdef _WIN32
extern void SUSSIX4DRIVENOISE (double *, double*, double*, double*, double*, double*, double*, double*, char*);
#define OS "Windows32"
#else
extern void sussix4drivenoise_(double *, double*, double*, double*, double*, double*, double*, double*, char*);
#define OS "linux"
#endif

    char   driveInputFilePath[2000], drivingTermsFilePath[2000], noiseFilePath[500]; /*TODO create size dynamically? (tbach)*/

    double calculatednattuney, calculatednattunex, calculatednatampy, calculatednatampx, co, co2, maxamp,
           windowa1, windowa2, windowb1, windowb2, noise1, maxfreq, maxmin, maxpeak, nattunex, nattuney, noiseAve;

    double allampsx[300], allampsy[300], allfreqsx[300], allfreqsy[300], amplitude[19], bpmpos[MAXPICK],
               doubleToSend[MAXTURNS4 + 4], matrix[MAXPICK][MAXTURNS], phase[19],
               tune[2];

    int labelrun, nslines=0, Nturns=0;

    int label[MAXPICK], hv[MAXPICK], hvt[MAXPICK];

#pragma omp threadprivate(amplitude, doubleToSend, tune, phase,\
        noise1, noiseAve, maxpeak, maxfreq, maxmin, co, co2,\
        allfreqsx, allampsx, allfreqsy, allampsy)

int main(int argc, char **argv)
{

    struct Data_Struct{
        size_t charCounter;

        double  istun, kper, tunex, tuney, nattunexsum, nattunex2sum, nattuneysum,
                nattuney2sum, tunesumx, tunesumy, tune2sumx, tune2sumy;

        int     counth, countv, kcase, kick, maxcounthv, Nbpms,
                pickstart, pickend, start, turns,
                tunecountx, tunecounty, nattunexcount, nattuneycount;
    };

    char    bpmFileName[300], dataFilePath[500], linxFilePath[2000],
            linyFilePath[2000], spectrumFilePath[400], string1[1000],
            string2[300], sussixInputFilePath[4000], workingDirectoryPath[4000];


    struct Data_Struct Data;


    int i, j, bpmCounter, columnCounter, horizontalBpmCounter, verticalBpmCounter, flag;

    char* lastSlashIndex;
    char* bpmname[MAXPICK];

    FILE *dataFile, *linxFile, *linyFile, *noiseFile, *spectrumFile, *driveInputFile,
            *drivingTermsFile;
        
    #ifdef _WIN32 /*Changes minor formatting difference in windows regarding the output of a number in scientific notation.*/
        _set_output_format(_TWO_DIGIT_EXPONENT);
    #endif  
    
    omp_set_dynamic(0);
    /* Memory allocation */

    for (i = 0; i < MAXPICK; i++)
        bpmname[i] = (char *) calloc(50, sizeof(char));

    /*  Path to DrivingTerms and Drive.inp */
    
    printf("%s\n",argv[1]);
    
    setPath(workingDirectoryPath, sizeof(workingDirectoryPath), argv[1], "", "");
    if (!canOpenFile(workingDirectoryPath) && OS == "linux") { /*Check always fails in windows*/
        fprintf(stderr, "Directory is not readable: %s\n", workingDirectoryPath);
        exit(EXIT_FAILURE);
    }
    else
        printf("\nWorking directory: %s\n", workingDirectoryPath);

    setPath(drivingTermsFilePath, sizeof(drivingTermsFilePath), workingDirectoryPath, "", "DrivingTerms");
    setPath(driveInputFilePath, sizeof(driveInputFilePath), workingDirectoryPath, "", "Drive.inp");
    setPath(sussixInputFilePath, sizeof(sussixInputFilePath), workingDirectoryPath, "", "sussix_v4.inp");



    /* check the file drivingTermsFilePath */
    if (!canOpenFile(drivingTermsFilePath)) {
        fprintf(stderr, "\nNo file %s for reading the name of the Data file\n", drivingTermsFilePath);
        exit(EXIT_FAILURE);
    }

    /* check the input file Drive.inp */
    if (!canOpenFile(driveInputFilePath)) {
        fprintf(stderr, "\nNo input file %s\n", driveInputFilePath);
        exit(EXIT_FAILURE);
    }


    /* set all options to defaults, it could happen that they are not included in the file (tbach) */
    Data.kick = Data.kcase = Data.pickstart = Data.pickend = labelrun = 0;
    Data.kper = Data.tunex = Data.tuney = Data.istun = windowa1 = windowa2 = windowb1 = windowb2 = 0.0;
    nattunex = nattuney = NATTUNE_DEFAULT;

    /* input/option file reading start */
    driveInputFile = getFileToRead(driveInputFilePath);
    while (1) {
        /* string1 will be the option name, s the value. expected separator: '=' (tbach) */
        for (Data.charCounter = 0; (Data.charCounter < sizeof(string1)) && ((string1[Data.charCounter] = (char)getc(driveInputFile)) != '=') &&
            (string1[Data.charCounter] != '\n') && (string1[Data.charCounter] != EOF); ++Data.charCounter) ;
        if (Data.charCounter >= sizeof(string1))
        {
            string1[Data.charCounter - 1] = '\0';
            fprintf(stderr, "Option name longer than sizeof(ss): %u, read: %s\n", sizeof(string1), string1);
            exit(EXIT_FAILURE);
        }
        if ((string1[Data.charCounter] == '\n') || (string1[Data.charCounter] == EOF)) /* we expect to have one '=' per line (tbach) */
            break;
        string1[Data.charCounter] = '\0'; /* '=' is replaced by string termination, this is ok (tbach) */


        for (Data.charCounter = 0; ((Data.charCounter < sizeof(string2)) && (string2[Data.charCounter] = (char)getc(driveInputFile)) != EOF) &&
            (string2[Data.charCounter] != '\n');)
        {
            /* if we have ' ' or '\t', do not increase counter and just overwrite them (tbach) */
            if (string2[Data.charCounter] == ' ' || string2[Data.charCounter] == '\t')
                printf("Found trailing(?) whitespace or tab for line with: %s (It is ignored, but should be removed)\n", string1);
            else
                ++Data.charCounter;
        }
        if (Data.charCounter >= sizeof(string2))
        {
            string2[Data.charCounter - 1] = '\0';
            fprintf(stderr, "Option value longer than sizeof(string2): %u, read: %s\n", sizeof(string2), string2);
            exit(EXIT_FAILURE);
        }
        string2[Data.charCounter] = '\0'; /* '\n' or 'EOF' is replaced by string termination, this is ok (tbach) */

        if (containsString(string1, "KICK") && strlen(string1) == 4) Data.kick = atoi(string2) - 1;     /* C arrays start at 0 */
        if (containsString(string1, "CASE")) Data.kcase = atoi(string2);
        if (containsString(string1, "KPER")) Data.kper = atof(string2);
        if (containsString(string1, "TUNE X")) Data.tunex = atof(string2);
        if (containsString(string1, "TUNE Y")) Data.tuney = atof(string2);
        if (containsString(string1, "PICKUP START")) Data.pickstart = atoi(string2);
        if (containsString(string1, "PICKUP END")) Data.pickend = atoi(string2);
        if (containsString(string1, "ISTUN")) Data.istun = atof(string2);
        if (containsString(string1, "LABEL")) labelrun = atoi(string2);
        if (containsString(string1, "WINDOWa1")) windowa1 = atof(string2);
        if (containsString(string1, "WINDOWa2")) windowa2 = atof(string2);
        if (containsString(string1, "WINDOWb1")) windowb1 = atof(string2);
        if (containsString(string1, "WINDOWb2")) windowb2 = atof(string2);
        if (containsString(string1, "NATURAL X")) nattunex = atof(string2);
        if (containsString(string1, "NATURAL Y")) nattuney = atof(string2);
    }
    fclose(driveInputFile);
    /* input/option file reading end */

    if (Data.kick >= 0)
        printf("Known kick in turn %d\n", Data.kick + 1);
    if (Data.kcase == 1)
        printf("Horizontal case\n");
    else if (Data.kcase == 0)
        printf("Vertical case\n");
    else {
        fprintf(stderr, "No proper kcase in Drive.inp\n");
        exit(EXIT_FAILURE);
    }

    if (labelrun == 1)
        printf("\n LABELRUN: NOISE FILES WILL BE WRITTEN TO NOISEPATH\n");
    printf("pickstart: %d, pickend: %d\n", Data.pickstart, Data.pickend);
    if (Data.pickstart < 0 || Data.pickstart > Data.pickend || Data.pickstart > MAXPICK) {
        fprintf(stderr, "Bad value for pickstart. Must be >= 0 and < Data.pickend and <= MAXPICK(=%d)\n", MAXPICK);
        exit(EXIT_FAILURE);
    }


    drivingTermsFile = getFileToRead(drivingTermsFilePath);
    Data.turns = 0;
    /* From drivingTermsFilePath assign dataFilePath, assign turns. */
    while (readDrivingTerms(drivingTermsFile, &(Data.turns), dataFilePath, sizeof(dataFilePath))) {
        /* set all values to be calculated to default values */
        Data.tunecountx = Data.tunecounty = Data.nattunexcount = Data.nattuneycount = 0;
        Data.tunesumx = Data.tunesumy = Data.tune2sumx = Data.tune2sumy = Data.nattunexsum = Data.nattunex2sum= Data.nattuneysum = Data.nattuney2sum = 0.0;

        /* Check the file dataFilePath */
        if (!canOpenFile(dataFilePath)) {
            /* doesn't exist --> try next one */
            printf("\nCan not open data file: %s\n", dataFilePath);
            continue;
        }
        printf("Data file: %s\n", dataFilePath);

        /*constructing name of output files */
        lastSlashIndex = dataFilePath;
        if (containsChar(dataFilePath, '/'))
            lastSlashIndex = strrchr(dataFilePath, '/') + 1; /* search last occurrence, subtract pointer. we search 2 times here, who cares (tbach) */

        /* copy everything from behind the last slash until the end to bpmFileName (tbach) */
        assertSmaller(strlen(lastSlashIndex), sizeof(bpmFileName), "set bpmfile");
        strncpy(bpmFileName, lastSlashIndex, sizeof(bpmFileName)); /* This could produce a not null terminated result, which is prevented by the assert (tbach) */
        printf("bpmFileName: %s\n", bpmFileName);

        setPath(noiseFilePath, sizeof(noiseFilePath), workingDirectoryPath, bpmFileName, "_noise");
        setPath(linxFilePath, sizeof(linxFilePath), workingDirectoryPath, bpmFileName, "_linx");
        setPath(linyFilePath, sizeof(linyFilePath), workingDirectoryPath, bpmFileName, "_liny");

        assertSmaller(strlen(bpmFileName) + strlen("_bpm"), sizeof(bpmFileName), "modify bpmFileName");
        strncat(bpmFileName, "_bpm", sizeof(bpmFileName) - strlen(bpmFileName) - 1);


        linxFile = getFileToWrite(linxFilePath);
        linyFile = getFileToWrite(linyFilePath);
        fprintf(linxFile,
                "* NAME S    BINDEX SLABEL TUNEX MUX  AMPX NOISE PK2PK AMP01 PHASE01 CO   CORMS AMP_20 PHASE_20 AMP02 PHASE02 AMP_30 PHASE_30 AMP_1_1 PHASE_1_1 AMP2_2 PHASE2_2 AMP0_2 PHASE0_2 NATTUNEX NATAMPX\n");
        fprintf(linxFile,
                "$ %%s  %%le %%le   %%le   %%le  %%le %%le %%le  %%le  %%le  %%le    %%le %%le  %%le   %%le     %%le  %%le    %%le   %%le     %%le    %%le      %%le   %%le     %%le   %%le     %%le     %%le\n");
        fprintf(linyFile,
                "* NAME S    BINDEX SLABEL TUNEY MUY  AMPY NOISE PK2PK AMP10 PHASE10 CO   CORMS AMP_1_1 PHASE_1_1 AMP_20 PHASE_20 AMP1_1 PHASE1_1 AMP0_2 PHASE0_2 AMP0_3 PHASE0_3 NATTUNEY NATAMPY\n");
        fprintf(linyFile,
                "$ %%s  %%le %%le   %%le   %%le  %%le %%le %%le  %%le  %%le  %%le    %%le %%le  %%le    %%le      %%le   %%le     %%le   %%le     %%le   %%le     %%le   %%le     %%le       %%le\n");

        if (labelrun == 1) noiseFile = getFileToWrite(noiseFilePath);


        flag = 0;
        for (i = 0; i < MAXPICK; i++)
            label[i] = 0;

        /* start data file reading, constructing a matrix with all the data from the pick-ups */
        bpmCounter = 0;
        columnCounter = 0;
        horizontalBpmCounter = -1;
        verticalBpmCounter = MAXPICK / 2 - 1;
        i = 0;
        dataFile = getFileToRead(dataFilePath);
        string1[0] = (char)getc(dataFile);
        while (string1[0] == '#') {       /* then it is a comment line (tbach) */
            while (getc(dataFile) != '\n');       /* read until the end of the line (tbach) */
            string1[0] = (char)getc(dataFile);        /* read the first char of the new line (tbach) */
        }
        /* after this, we have skipped all the comment lines, and s[0] is the first character of a new line which is not a "#" (tbach) */
        if (LOG_INFO)
            printf("BPM file content:\n");
        while (string1[0] != EOF) {
            if (string1[0] == '\n') {
                ++bpmCounter;
                if (LOG_INFO)
                    printf("\n");
                columnCounter = 0;
            }
            if (isspace((int)string1[0]) && flag == 1)
                flag = 0;
            if (!isspace((int)string1[0]) && flag == 0) {
                while (!isspace((int)string1[i]) && string1[i] != EOF) {
                    ++i;
                    string1[i] = (char)getc(dataFile);
                    if (i > 100) {
                        string1[i + 1] = '\0';
                        fprintf(stderr, "Found a value which has more than 100 characters, exit parsing.\n"
                            "This is most probably a malformatted file. bpmCounter=%d columnCounter=%d string1=%s\n", bpmCounter, columnCounter, string1);
                        exit(EXIT_FAILURE);
                    }
                }
                string1[i + 1] = string1[i];
                string1[i] = '\0';
                if (LOG_INFO)
                    printf("%s ", string1);
                if (columnCounter >= MAXTURNS) {
                    fprintf(stderr, "Found >= %d Turns, this turn size is not supported. Reduce amount of turns. bpmCounter:%d\n", MAXTURNS - 3, bpmCounter); /* 0,1,2 is plane, name and location (tbach) */
                    exit(EXIT_FAILURE);
                }
                if (bpmCounter >= MAXPICK) {
                    fprintf(stderr, "Found >= %d BPMs, this size is not supported. Reduce amount of BPMs. columnCounter:%d\n", MAXPICK, columnCounter);
                    exit(EXIT_FAILURE);
                }
                if (columnCounter == 0) {   /*plane (tbach) */
                    hv[bpmCounter] = atoi(string1);
                    if (hv[bpmCounter] == 0) /* 0 is horizontal, 1 is vertical (tbach) */
                        ++horizontalBpmCounter;
                    else
                        ++verticalBpmCounter;
                }

                else if (columnCounter == 1) {   /*bpm name (tbach) */
                    if (hv[bpmCounter] == 0) {
                        if (horizontalBpmCounter < 0) /* Branch prediction will cry, but well lets have security (tbach) */
                        {
                            fprintf(stderr, "horizontalBpmCounter < 0. Should not happen. Probably malformatted input file?\n");
                            exit(EXIT_FAILURE);
                        }
                        hvt[horizontalBpmCounter] = 0;
                        strcpy(bpmname[horizontalBpmCounter], string1);
                        label[horizontalBpmCounter] = 1;
                    } else {
                        hvt[verticalBpmCounter] = 1;
                        strcpy(bpmname[verticalBpmCounter], string1);
                        label[verticalBpmCounter] = 1;
                    }
                }

                else if (columnCounter == 2) {   /*bpm location (tbach) */
                    if (hv[bpmCounter] == 0)
                    {
                        if (horizontalBpmCounter < 0) /* Branch prediction will cry, but well lets have security (tbach) */
                        {
                            fprintf(stderr, "horizontalBpmCounter < 0. Should not happen. Probably malformatted input file?\n");
                            exit(EXIT_FAILURE);
                        }
                        bpmpos[horizontalBpmCounter] = atof(string1);
                    }
                    else
                        bpmpos[verticalBpmCounter] = atof(string1);
                }

                else {    /*bpm data (tbach) */
                    if (hv[bpmCounter] == 0)
                        matrix[horizontalBpmCounter][columnCounter - 3] = atof(string1);
                    else
                        matrix[verticalBpmCounter][columnCounter - 3] = atof(string1);
                    Nturns = columnCounter - 3 + 1;
                    /* If the last line is an empty line, then we can get the number of turns only from here.
                       First 3 are plane, name and location.
                       Plus 1 for index start at 0
                       (tbach) */
                }
                ++columnCounter;
                flag = 1;
                string1[0] = string1[i + 1];
                i = 0;
            }
            if (flag == 0)
                string1[0] = (char)getc(dataFile);
        }
        fclose(dataFile);

        Data.Nbpms = bpmCounter;
        Data.counth = horizontalBpmCounter + 1;
        Data.countv = verticalBpmCounter + 1;

        /* now redefine turns as the minimum of the Nturns read and the DrivingTerms data card */
        /* NB assumes all BPMs have the same number of turns as the last one read is used */
        if (Data.turns > Nturns) Data.turns = Nturns;

        /* Some statistics and checks */
        printf("Total number of pick-ups: %d Last turn number: %d, turns to run: %d\n", Data.Nbpms, Nturns, Data.turns);
        printf("Horizontal pick-ups: %d   Vertical pick-ups: %d\n", Data.counth, -MAXPICK / 2 + Data.countv);
        printf("name of BPM[0]: %s, pos: %f, first turn: %f, second turn: %f, last turn: %f, last turn to run: %f \n",
             bpmname[0], bpmpos[0], matrix[0][0], matrix[0][1], matrix[0][Nturns - 1], matrix[0][Data.turns - 1]);
        /* end of data file reading */

        printf("kick: %d \n", Data.kick);
        /* searching for two working adjacent pick-ups */
        /* after the Q-kickers for finding the kick */
        if (Data.kick < 0) {
            Data.start = -(Data.kcase - 1) * MAXPICK / 2 + 2;
            while (label[Data.start] == 0 || label[Data.start + 2] == 0) {
                Data.start = Data.start + 2;
            }

            printf("looking for kick in pick-up:%d\n", Data.start + 1);
            /* Find kick here and get kick */
            for (columnCounter = 1; (Data.kick < 0) && (columnCounter < Data.turns); ++columnCounter) {
                if (fabs(matrix[Data.start][columnCounter] - matrix[Data.start][columnCounter - 1]) > Data.kper) {
                    Data.kick = columnCounter;
                }
            }

            if (Data.kick < 0) {
                fprintf(stderr, "NO KICK FOUND\n");
                exit(EXIT_FAILURE);
            } else
                printf("Found kick in turn:%d\n", Data.kick + 1);    /*Natural count */
        }

        if (Data.kick > 0) {
            for (i = 0; i < MAXPICK; i++) {
                if (label[i] == 1) {
                    for (j = Data.kick; j < Data.turns; j++)
                        matrix[i][j - Data.kick] = matrix[i][j];
                }
            }
            Data.turns -= Data.kick;
        }
        printf("Turns to be processed after kick offset: %d matrix[0][0]: %f \n", Data.turns, matrix[0][0]);

        /* First part of the analysis: Determine  phase of all pick-ups and noise */
        writeSussixInput(sussixInputFilePath, Data.turns, Data.istun, Data.tunex, Data.tuney);

        if (Data.counth >= (Data.countv - MAXPICK / 2))
            Data.maxcounthv = Data.counth;
        else
            Data.maxcounthv = -MAXPICK / 2 + Data.countv;

        if (Data.maxcounthv > Data.pickend)
            Data.maxcounthv = Data.pickend;
        /*Shouldn't this check if counth+(countv-MAXPICK/2)>MAXPICK?*/
        if (Data.maxcounthv >= MAXPICK) {
            fprintf(stderr, "\nNot enough Pick-up mexmory\n");
            exit(EXIT_FAILURE);
        }
        printf("BPMs in loop: %d, pickstart: %d, resulting loop length: %d\n",
             Data.maxcounthv, Data.pickstart, Data.maxcounthv - Data.pickstart);

#pragma omp parallel for private(i, horizontalBpmCounter, verticalBpmCounter, j, maxamp, calculatednattunex, calculatednattuney, calculatednatampx, calculatednatampy)
        for (i = Data.pickstart; i < Data.maxcounthv; ++i) {
            horizontalBpmCounter = i;
            verticalBpmCounter = i + MAXPICK / 2;

            if (verticalBpmCounter >= Data.countv)
                verticalBpmCounter = Data.countv - 1;
            if (horizontalBpmCounter >= Data.counth)
                horizontalBpmCounter = Data.counth - 1;
            if (horizontalBpmCounter < 0 || verticalBpmCounter < 0)
            {
                fprintf(stderr, "horizontal or vertical BpmCounter < 0. Should not happen.\n");
                exit(EXIT_FAILURE);
            }
            /*printf("BPM indexes (H,V):%d %d\n", horizontalBpmCounter, verticalBpmCounter); This is not synchronised and can produce random ordered output for multiple threads (tbach) 
            Commented out because it provides no information and makes output even messier (asherman)*/

            for (j = 0; j < MAXTURNS; ++j) {
                doubleToSend[j] = matrix[horizontalBpmCounter][j];
                doubleToSend[j + MAXTURNS] = matrix[verticalBpmCounter][j];
                doubleToSend[j + 2 * MAXTURNS] = 0.0;
                doubleToSend[j + 3 * MAXTURNS] = 0.0;
            }


            /* This calls the external Fortran code (tbach)-Different name depending on OS (asherman)*/
            #ifdef _WIN32
                SUSSIX4DRIVENOISE (&doubleToSend[0], &tune[0], &amplitude[0], &phase[0], &allfreqsx[0], &allampsx[0], &allfreqsy[0], &allampsy[0], sussixInputFilePath);
            #else
                sussix4drivenoise_(&doubleToSend[0], &tune[0], &amplitude[0], &phase[0], &allfreqsx[0], &allampsx[0], &allfreqsy[0], &allampsy[0], sussixInputFilePath);
            #endif
            /* Let's look for natural tunes in the istun range if natural tunes input is given*/
            maxamp = 0;
            calculatednattunex = NATTUNE_DEFAULT;
            if (nattunex > NATTUNE_DEFAULT) {
                for (j = 0; j < 300; ++j) {
                    if ((nattunex - Data.istun < allfreqsx[j] && allfreqsx[j] < nattunex + Data.istun) && (maxamp < allampsx[j])) {
                        maxamp = allampsx[j];
                        calculatednattunex = allfreqsx[j];
                        calculatednatampx = maxamp;
                    }
                }
            }
            maxamp = 0;
            calculatednattuney = NATTUNE_DEFAULT;
            if (nattuney > NATTUNE_DEFAULT) {
                for (j = 0; j < 300; ++j) {
                    if ((nattuney - Data.istun < allfreqsy[j] && allfreqsy[j] < nattuney + Data.istun) && (maxamp < allampsy[j])) {
                        maxamp = allampsy[j];
                        calculatednattuney = allfreqsy[j];
                        calculatednatampy = maxamp;
                    }
                }
            }

            #pragma omp critical
            {
                label[horizontalBpmCounter] = BPMstatus(1, Data.turns);
                if (labelrun == 1)
                    fprintf(noiseFile, "1 %d  %e %e %e %e %e %d %d %f\n",
                            horizontalBpmCounter, noise1, noiseAve, maxpeak, maxfreq, maxmin, nslines, label[i], phase[0] / 360.);

                /* PRINT LINEAR FILE */
                if (amplitude[0] > 0 && label[i] == 1 && horizontalBpmCounter == i) {
                    fprintf(linxFile, "\"%s\" %e %d %d %e %e %e %e %e %e %e %e %e %e %e %e %e %e %e %e %e %e %e %e %e %e %e\n",
                            bpmname[horizontalBpmCounter], bpmpos[horizontalBpmCounter], horizontalBpmCounter, label[horizontalBpmCounter], tune[0],
                            phase[0] / 360., amplitude[0], noise1, maxmin, amplitude[2] / amplitude[0], phase[2] / 360.,
                            co, co2, amplitude[1] / amplitude[0],
                            phase[1] / 360., amplitude[12] / amplitude[0], phase[12] / 360., amplitude[6] / amplitude[0],
                            phase[6] / 360., amplitude[14] / amplitude[0], phase[14] / 360., amplitude[16] / amplitude[0],
                            phase[16] / 360., amplitude[18] / amplitude[0], phase[18] / 360.,  calculatednattunex, calculatednatampx );
                    ++Data.tunecountx;
                    Data.tunesumx += tune[0];
                    Data.tune2sumx += tune[0] * tune[0];
                    if (calculatednattunex > NATTUNE_DEFAULT) { /*  Initialized to -100. Condition true if nat tune found */
                        ++Data.nattunexcount;
                        Data.nattunexsum += calculatednattunex;
                        Data.nattunex2sum += calculatednattunex * calculatednattunex;
                    }

                    /* Horizontal Spectrum output */
                    if (i < 10) {
                        setPath(spectrumFilePath, sizeof(spectrumFilePath), workingDirectoryPath, bpmname[i], ".x");
                        spectrumFile = getFileToWrite(spectrumFilePath);
                        fprintf(spectrumFile, "%s %s %s\n", "*", "FREQ", "AMP");
                        fprintf(spectrumFile, "%s %s %s\n", "$", "%le", "%le");
                        for (j = 0; j < 300; ++j)
                            fprintf(spectrumFile, "%e %e\n", allfreqsx[j], allampsx[j]);
                        fclose(spectrumFile);
                    }
                }
                label[verticalBpmCounter] = BPMstatus(2, Data.turns);
                if (labelrun == 1)
                    fprintf(noiseFile, "2 %d  %e %e %e %e %e %d %d %f\n",
                            verticalBpmCounter, noise1, noiseAve, maxpeak, maxfreq, maxmin, nslines, label[verticalBpmCounter], phase[3] / 360.);
                if (amplitude[3] > 0 && label[verticalBpmCounter] == 1 && verticalBpmCounter == i + MAXPICK / 2) {
                    fprintf(linyFile, "\"%s\" %e %d %d %e %e %e %e %e %e %e %e %e %e %e %e %e %e %e %e %e %e %e %e %e\n",
                            bpmname[verticalBpmCounter], bpmpos[verticalBpmCounter], verticalBpmCounter, label[verticalBpmCounter], tune[1], phase[3] / 360., amplitude[3], noise1,
                            maxmin, amplitude[5] / amplitude[3], phase[5] / 360., co, co2,
                            amplitude[13] / amplitude[3], phase[13] / 360., amplitude[15] / amplitude[3], phase[15] / 360.,
                            amplitude[17] / amplitude[3], phase[17] / 360., amplitude[4] / amplitude[3], phase[4] / 360.,
                            amplitude[11] / amplitude[3], phase[11] / 360., calculatednattuney, calculatednatampy);
                    ++Data.tunecounty;
                    Data.tunesumy += tune[1];
                    Data.tune2sumy += tune[1] * tune[1];
                    if (calculatednattuney > NATTUNE_DEFAULT) { /*  Initialized to -100. Condition true if nat tune found */
                        ++Data.nattuneycount;
                        Data.nattuneysum += calculatednattuney;
                        Data.nattuney2sum += calculatednattuney * calculatednattuney;
                    }
                    if (verticalBpmCounter < MAXPICK / 2 + 10) {
                        setPath(spectrumFilePath, sizeof(spectrumFilePath), workingDirectoryPath, bpmname[verticalBpmCounter], ".y");
                        spectrumFile = getFileToWrite(spectrumFilePath);
                        fprintf(spectrumFile, "%s %s %s\n", "*", "FREQ", "AMP");
                        fprintf(spectrumFile, "%s %s %s\n", "$", "%le", "%le");
                        for (j = 0; j < 300; ++j)
                            fprintf(spectrumFile, "%e %e \n", allfreqsy[j], allampsy[j]);
                        fclose(spectrumFile);
                    }
                }
            } /* end of omp critical section */
        } /* end of parallel for */
        fclose(linxFile);
        fclose(linyFile);
        if (labelrun == 1) fclose(noiseFile);

        /* Sort and move the "@..." lines to the top of the _linx/y files */
        formatLinFile(linxFilePath,
                Data.tunecountx, Data.tunesumx, Data.tune2sumx, "@ Q1 %%le %e\n@ Q1RMS %%le %e\n",
                Data.nattunexcount, Data.nattunexsum, Data.nattunex2sum, "@ NATQ1 %%le %e\n@ NATQ1RMS %%le %e\n");
        formatLinFile(linyFilePath,
                Data.tunecounty, Data.tunesumy, Data.tune2sumy, "@ Q2 %%le %e\n@ Q2RMS %%le %e\n",
                Data.nattuneycount, Data.nattuneysum, Data.nattuney2sum, "@ NATQ2 %%le %e\n@ NATQ2RMS %%le %e\n");
    } /* end of while loop over all files to analyse */
    fclose(drivingTermsFile);

    return EXIT_SUCCESS;
}

/* *****************  */
/*    readDrivingTerms*/
/* *****************  */
int readDrivingTerms(FILE* drivingTermsFile, int* turns, char* path, const int sizeOfPath)
{
    /* This functions reads from the given FILE one line of this format:
     * <path to datafile> <int start turn> <int end turn>
     * If a line was successfully read, return true
     * If not, return false
     * --tbach */

    int charCounter = 0;

    /* this block reads the filepath */
    while (isspace((int)(path[0] = (char)getc(drivingTermsFile))));
    if(OS == "Windows32") { /*Path may not exist if drivingtermsfile was created on linux, so this deals with that. (Assumes /afs/cern.ch is 'H' drive)*/
    for (charCounter=1;((charCounter < sizeOfPath && (path[charCounter] = (char)getc(drivingTermsFile)) != EOF) &&
         (path[charCounter] != '\n') && (path[charCounter] != '%') &&
         (path[charCounter] != ' ')); charCounter++){
            path[charCounter+1] = '\0';  /*Necessary for use of strcmp*/
            if(strcmp(path,"/afs/cern.ch") == 0){
                path[0] = 'H';
                path[1] = ':';
                charCounter = 1;
            }
         }
    }
    
    else
        for (charCounter = 1; ((charCounter < sizeOfPath && (path[charCounter] = (char)getc(drivingTermsFile)) != EOF) &&
         (path[charCounter] != '\n') && (path[charCounter] != '%') &&
         (path[charCounter] != ' ')); charCounter++) ;
    
    if (charCounter >= sizeOfPath)
    {
        fprintf(stderr, "Error: path longer than sizeOfPath: %d\n", sizeOfPath);
        exit(EXIT_FAILURE);
    }
    if (path[charCounter] == EOF) { /* we do not expect an EOF here (tbach)*/
        path[charCounter] = '\0';
        return 0;
    }
    path[charCounter] = '\0';

    /* this block reads over the first number (tbach) */
    if (getNextInt(drivingTermsFile) == EOF)
        return 0;

    /* this block reads the second number (tbach) */
    *turns = getNextInt(drivingTermsFile);
    if (*turns == EOF)
        return 0;
    return 1;
}

int getNextInt(FILE* file)
{
    /* This reads the next int from the given file.
     * - skips ' '
     * - reads everything until EOF, '\n' or ' ' into some <var>
     * - converts the found char in <var> to int
     * - returns the int or EOF if something went wrong
     * --tbach */
    int result = 0;
    char string1[1000];
    size_t charCounter = 0;
    while (isspace((int)(string1[0] = (char)getc(file)))) ;  /* skip all spaces (tbach) */
    if (string1[0] == EOF)
        return EOF;
    for (charCounter = 1; ((charCounter < sizeof(string1)) && (string1[charCounter] = (char)getc(file)) != EOF) &&
         (string1[charCounter] != '\n') && (string1[charCounter] != ' '); charCounter++) ;
    if (charCounter >= sizeof(string1))
    {
        string1[charCounter - 1] = '\0';
        fprintf(stderr, "Error: input longer than sizeof(string1): %u, string1: %s\n", sizeof(string1), string1);
        exit(EXIT_FAILURE);
    }
    string1[charCounter] = '\0';
    result = atoi(string1);
    return result;
}

/* ***************** */
/*    sussix_inp     */
/* ***************** */
void writeSussixInput(const char* sussixInputFilePath, const int turns, const double istun, const double tunex, const double tuney)
{
    FILE* sussixInputFile = getFileToWrite(sussixInputFilePath);
    fprintf(sussixInputFile, "C\n");
    fprintf(sussixInputFile, "C INPUT FOR SUSSIX_V4 ---17/09/1997---\n");
    fprintf(sussixInputFile, "C DETAILS ARE IN THE MAIN PROGRAM SUSSIX_V4.F\n");
    fprintf(sussixInputFile, "C\n");
    fprintf(sussixInputFile, "\n");
    fprintf(sussixInputFile, "ISIX  = 0\n");
    fprintf(sussixInputFile, "NTOT  = 1\n");
    fprintf(sussixInputFile, "IANA  = 1\n");
    fprintf(sussixInputFile, "ICONV = 0\n");
    fprintf(sussixInputFile, "TURNS = 1 %d\n", turns);
    fprintf(sussixInputFile, "NARM  = 300\n");
    fprintf(sussixInputFile, "ISTUN = 1 %e %e\n", istun, istun);
    fprintf(sussixInputFile, "TUNES = %e %e .07\n", tunex, tuney);
    fprintf(sussixInputFile, "NSUS  = 0\n");
    fprintf(sussixInputFile, "IDAM  = 2\n");
    fprintf(sussixInputFile, "NTWIX = 1\n");
    fprintf(sussixInputFile, "IR    = 1\n");
    fprintf(sussixInputFile, "IMETH = 2\n");
    fprintf(sussixInputFile, "NRC   = 4\n");
    fprintf(sussixInputFile, "EPS   = 2D-3\n"); /* EPS is the window in the secondary lines, very imp!!! */
    fprintf(sussixInputFile, "NLINE = 0\n");
    fprintf(sussixInputFile, "L,M,K = \n");
    fprintf(sussixInputFile, "IDAMX = 1\n");
    fprintf(sussixInputFile, "NFIN  = 500\n");
    fprintf(sussixInputFile, "ISME  = 0\n");
    fprintf(sussixInputFile, "IUSME = 200\n");
    fprintf(sussixInputFile, "INV   = 0\n");
    fprintf(sussixInputFile, "IINV  = 250\n");
    fprintf(sussixInputFile, "ICF   = 0\n");
    fprintf(sussixInputFile, "IICF  = 350\n");
    fclose(sussixInputFile);
}

/************   BPMstatus *************/
/* Analyse fort.300 to detect noise   */
/**************************************/

/*UPDATE: All rejections are removed from this code, as other parts
 * of Beta-beat are in charge of rejecting now.  Calculations are still
 * kept in place. --asherman (07/2013)
 */
#define MINSIGNAL 0.00001
#define SIGMACUT   1.8
#define MINIMUMNOISE 0.0
#define BADPICKUP  8.0
#define MAXSIGNAL 30000
int BPMstatus(const int plane, const int turns)
{
    double aux = 0, ave = 0, amp = 0,
        maxe = -500000.0, mine = 500000.0;
    int i,j = 0;

    maxpeak = 0;                /*Initialising */
    co = 0.0;
    co2 = 0.0;
    /* If peak-to-peak signal smaller than MINSIGNAL reject
     * Update: No longer, see above*/
    if (plane == 1) {
        for (i = 0; i < turns; i++) {
            co += doubleToSend[i];
            co2 += doubleToSend[i] * doubleToSend[i];
            if (doubleToSend[i] < mine)
                mine = doubleToSend[i];
            if (doubleToSend[i] > maxe)
                maxe = doubleToSend[i];
        }
    }
    if (plane == 2) {
        for (i = MAXTURNS; i < MAXTURNS + turns; i++) {
            co += doubleToSend[i];
            co2 += doubleToSend[i] * doubleToSend[i];
            if (doubleToSend[i] < mine)
                mine = doubleToSend[i];
            if (doubleToSend[i] > maxe)
                maxe = doubleToSend[i];
        }
    }
    co = co / turns;
    co2 = sqrt(co2 / turns - co * co);
    maxmin = maxe - mine;

    /*if (maxmin < MINSIGNAL || maxmin > MAXSIGNAL)
            return 0;*/
    /* Compute the spread and average in the intervals [windowa1,windowa2]
       and [windowb1,windowb2] */

    noise1 = 0;

    for (i = 0; i < 300; i++) {
        if (plane == 1) {
            aux = allfreqsx[i];
            amp = allampsx[i];
        }
        else if (plane == 2) {
            aux = allfreqsy[i];
            amp = allampsy[i];
        }

        if (amp > maxpeak && aux > 0.05) {
            maxpeak = amp;
            maxfreq = aux;
        }

        if ((aux < windowa2 && aux > windowa1)
            || (aux < windowb2 && aux > windowb1)) {
            if (amp < 0) {      /* Something in sussix went wrong */
                noise1 = 100;
                noiseAve = 100;
                maxpeak = 100;
                maxfreq = 100;
                /*return 0;*/
            }

            ave = amp + ave;
            noise1 = noise1 + amp * amp;
            ++j;
        }

    }
    if (j > 0) {
        if (j > 1)
            noise1 = sqrt((noise1 / j - ave * ave / (j*j)));
        else
            noise1 = 0;
        noiseAve = ave / j;
    } else {
        noise1 = MINIMUMNOISE;
        noiseAve = MINIMUMNOISE;
    }
    nslines = j;

    /* If tune line isn't larger than background reject
     * Update: No longer, see above */

    if ((windowa1 < maxfreq && maxfreq < windowa2)
     || (windowb1 < maxfreq && maxfreq < windowb2))
        printf("NoiseWindow includes largest lines, amp %e freq %e!!!!\n",
               maxpeak, maxfreq);

    /*if (maxpeak <= noiseAve + SIGMACUT * noise1)
        return 0;

    if (noise1 > BADPICKUP)
        return 0;*/

     /*Otherwise pick-up succeeded to first cuts*/ 
    return 1;
}

int containsChar(const char* string, const char character)
{
    return (strchr(string, character) != NULL);
}

int containsString(const char* string1, const char* string2)
{
    return (strstr(string1, string2) != NULL);
}

int canOpenFile(const char* const filename)
{
    FILE* file;
    if ((file = fopen(filename, "r")) == NULL)
        return 0;
    fclose(file);
    return 1;
}

FILE* getFileToWrite(const char* const filename)
{
    return __getFileWithMode(filename, "w", "Cannot open to write: %s\n");
}

FILE* getFileToRead(const char* const filename)
{
    return __getFileWithMode(filename, "r", "Cannot open to read: %s\n");
}

FILE* __getFileWithMode(const char* const filename, const char* const mode, const char* const errormessage)
{
    FILE* file = fopen(filename, mode);
    if (file == NULL)
    {
        fprintf(stderr, errormessage, filename);
        exit(EXIT_FAILURE);
    }
    return file;
}

void assertSmaller(const int a, const int b, const char* message)
{
    if (a < b)
        return;
    fprintf(stderr, "Value1: %d is not < than Value2: %d. Message: %s\n", a, b, message);
    exit(EXIT_FAILURE);
}

void setPath(char* path, const size_t sizeOfPath, const char* workingDirectoryPath, const char* bpmfile, const char* fileEnding)
{
    /* sets path to <workingDirectoryPath>/<bpmfilefile><Ending> (tbach) */
    assertSmaller(strlen(workingDirectoryPath) + 1 + strlen(bpmfile) + strlen(fileEnding), sizeOfPath, fileEnding);
    sprintf(path, "%s/%s%s", workingDirectoryPath, bpmfile, fileEnding);
    printf("%s: %s\n", fileEnding, path);
}


/* what is happening here? we want to sort the lin file and put 2 lines on top.
     * We could do this in plain c, but it is a bit of work, so we use shell tools.
     * (this breaks OS compatibility, but this is not a priority right now)
     * So we put calculations for tune at a temp file.
     * Then we add the first 2 lines (column headers) to temp file
     * Then we sort all files from the third line to the end, but them in the temp file (sorted)
     * Then we rename the temp file to orig file
     * --tbach*/

/*UPDATE:  Use of shell has been eliminated, uses only c allowing for OS compatability
 * -- asherman (07/2013) */

void formatLinFile(const char* linFilePath,
        const int tunecount, const double tunesum, const double tune2sum, const char* tuneheader,
        const int nattunecount, const double nattunesum, const double nattune2sum, const char* nattuneheader) {

    char tempFilePath[2000], string[1500], num[6], *fileHolder[MAXPICK];
    FILE *tempFile, *linFile;
    int i, j=0, k, flag, max=0, min = 1300, end=0, bIndex;


    if (tunecount > 0) {
        /*Memory allocation for fileHolder*/
        for (bIndex = 0; bIndex < MAXPICK; bIndex++)
               fileHolder[bIndex] = (char *) calloc(1000, sizeof(char));

        sprintf(tempFilePath, "%s_temp", linFilePath);
        tempFile = getFileToWrite(tempFilePath);

        printTuneValue(tempFile, tuneheader, tunecount, tunesum, tune2sum);
        if (nattunecount > 0)
            printTuneValue(tempFile, nattuneheader, nattunecount, nattunesum, nattune2sum);

        /*Gets linFile to read*/
        linFile = getFileToRead(linFilePath);
        
        /*Writes first two lines from lineFile into tempFile.*/
        for(i = 0;i < 1500 && j < 2;i++){
            string[i] = (char)fgetc(linFile);
            if(string[i] == '\n')
                j++;
        }

        if(i == 1500){
            printf("First two lines of %s are too long.\n", linFilePath);
            exit(EXIT_FAILURE);
        }
        
        for(i = 0, j = 0;i < 1500 && j < 2;i++){
            fputc(string[i],tempFile);
            if(string[i] == '\n')
                j++;
        }

        /*Begins loop which simultaneously places lines of linFile
         * into fileHolder and sorts them according to bIndex which
         * is an integer in the third column of each line.
         */
        while(end != 1){
            flag = j = k = 0;

            for(i=0;i<1500;i++){
                string[i] = (char)getc(linFile);
                if(i == 0 && string[i] == '"')
                    flag = 1;
                if(flag == 1){
                    if(string[i] == ' ' && string[i-1] != ' '){
                        j++;
                    }
                    if(j == 2 && string[i] != ' '){
                        num[k]=string[i];
                        k++;
                    }
                }
                if(string[i] == '\n')
                    break;
                if(string[i] == EOF){
                    end = 1;
                    break;
                }
            }

            if(flag == 1){
                num[k]='\0';
                bIndex = atoi(num);
            }

            if(i == 1500){
                if(flag == 1)
                    printf("Line with bIndex %d in file %s is too long.\n", bIndex, linFilePath);
                else
                    printf("Line with no bIndex in file %s is too long.\n",linFilePath);
                exit(EXIT_FAILURE);
            }

           if(flag == 1){
                if(bIndex > max) /*Finds highest bIndex in linFile*/
                    max = bIndex;
                if(bIndex < min) /*Finds lowest bIndex in linFile*/
                    min = bIndex;
                for(i = 0;i < 1500; i++){ /*Places lines into fileHolder in sorted fashion*/
                    fileHolder[bIndex][i] = string[i];
                    if(string[i] == '\n' || string[i]== EOF)
                        break;
                }
            }
        }

        /*Writes sorted lines into tempfile*/
       for(bIndex = min;bIndex <= max;bIndex++){
            for(i=0;i<1500;i++){
                if(fileHolder[bIndex][0] != '"')
                    break;
                fputc(fileHolder[bIndex][i],tempFile);
                if(fileHolder[bIndex][i] == '\n' || fileHolder[bIndex][i] == EOF)
                    break;
            }
            if(fileHolder[bIndex][i] == EOF)
                break;
        }

        /*Removes linFile, renames tempFile to linFile*/
        fclose(tempFile);
        fclose(linFile);
        remove(linFilePath);
        rename(tempFilePath, linFilePath);

        printf("%s:\ntune: \n  sum: %e, count: %d, sum2: %e \nnatural tune: \n  sum: %e, count: %d, sum2: %e\n",
                linFilePath, tunesum, tunecount, tune2sum, nattunesum,
                nattunecount, nattune2sum);
    }
}


void printTuneValue(FILE* linFile, const char* header, const int count, const double tunesum, const double tune2sum)
{
    /* calculates the average and the RMS(?) (tbach) */
    fprintf(linFile, header,
            tunesum / count,
            sqrt(tune2sum / count - (tunesum / count) * (tunesum / count)));
}
